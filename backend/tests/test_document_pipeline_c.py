import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from bson import ObjectId

from modules.documents.repository import MongoDocumentRepository
from modules.ocr.easyocr_engine import extract_pdf_text_pages, extract_text_or_ocr_pdf
from modules.ocr.pipeline import clean_text_basic, remove_headers_footers
from modules.ocr.text_cleaner import clean_ocr_pages


class OcrSourceIntegrityTests(unittest.TestCase):
    @staticmethod
    def _make_pdf(path: Path, texts: list[str], **save_options) -> None:
        import fitz

        document = fitz.open()
        for text in texts:
            page = document.new_page()
            if text:
                page.insert_text((72, 72), text)
        document.save(path, **save_options)
        document.close()

    def test_cleaning_preserves_raw_metadata_code_symbols_and_indentation(self):
        raw = "int main() {\n    if (a <= b && p != nullptr) {\n        p = p->next;\n    }\n}"
        page = {
            "page_number": 1,
            "text": raw,
            "original_text": raw,
            "extraction_method": "OCR",
            "quality_flags": ["VISUAL_REVIEW_REQUIRED"],
            "layout_blocks": [{"type": "TEXT", "bbox": [0, 0, 1, 1]}],
        }

        result = clean_ocr_pages(clean_text_basic(remove_headers_footers([page])))[0]

        self.assertEqual(result["original_text"], raw)
        self.assertEqual(result["extraction_method"], "OCR")
        self.assertEqual(result["quality_flags"], ["VISUAL_REVIEW_REQUIRED"])
        self.assertIn("        p = p->next;", result["text"])
        self.assertIn("<=", result["text"])
        self.assertIn("&&", result["text"])
        self.assertIn("!=", result["text"])

    def test_header_removal_does_not_drop_raw_or_layout_metadata(self):
        pages = [
            {
                "page_number": number,
                "text": f"Repeated Header\nBody page {number}\n{number}",
                "original_text": f"raw page {number}",
                "layout_blocks": [{"page": number}],
                "extraction_method": "TEXT",
            }
            for number in range(1, 4)
        ]

        cleaned = remove_headers_footers(pages)

        self.assertEqual([page["original_text"] for page in cleaned], ["raw page 1", "raw page 2", "raw page 3"])
        self.assertEqual(cleaned[1]["layout_blocks"], [{"page": 2}])

    def test_extraction_first_only_ocrs_pages_without_usable_text(self):
        extracted = [
            {
                "page_number": 1,
                "text": "native text",
                "original_text": "native text",
                "extraction_method": "TEXT",
                "quality_flags": [],
                "layout_blocks": [],
                "visual_blocks": [],
            },
            {
                "page_number": 2,
                "text": "",
                "original_text": "",
                "extraction_method": "OCR_PENDING",
                "quality_flags": ["TEXT_LAYER_INSUFFICIENT", "VISUAL_REVIEW_REQUIRED"],
                "layout_blocks": [],
                "visual_blocks": [{"id": "VISUAL-P2-1"}],
            },
        ]
        ocr = [
            {
                "page_number": 2,
                "text": "ocr text",
                "original_text": "ocr text",
                "extraction_method": "OCR",
                "quality_flags": [],
                "layout_blocks": [],
            }
        ]
        with (
            patch("modules.ocr.easyocr_engine.extract_pdf_text_pages", return_value=extracted),
            patch("modules.ocr.easyocr_engine.stream_and_ocr_pdf", return_value=ocr) as fallback,
        ):
            result = extract_text_or_ocr_pdf("sample.pdf", ["vi", "en"])

        self.assertEqual(result[0]["extraction_method"], "TEXT")
        self.assertEqual(result[1]["extraction_method"], "OCR")
        self.assertEqual(result[1]["visual_blocks"][0]["id"], "VISUAL-P2-1")
        self.assertEqual(fallback.call_args.kwargs["page_numbers"], [2])

    def test_corrupt_pdf_has_a_stable_validation_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.pdf"
            path.write_bytes(b"not a pdf")
            with self.assertRaisesRegex(ValueError, "bị hỏng"):
                extract_pdf_text_pages(str(path))

    def test_native_text_pdf_is_extracted_without_easyocr(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "text.pdf"
            text = "Cấu trúc dữ liệu hàng đợi FIFO. " * 8
            self._make_pdf(path, [text])
            with patch("modules.ocr.easyocr_engine.stream_and_ocr_pdf") as fallback:
                pages = extract_text_or_ocr_pdf(str(path), ["vi", "en"])

        self.assertEqual(pages[0]["extraction_method"], "TEXT")
        self.assertIn("FIFO", pages[0]["original_text"])
        fallback.assert_not_called()

    def test_encrypted_pdf_is_rejected_explicitly(self):
        import fitz

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "encrypted.pdf"
            self._make_pdf(
                path,
                ["protected source"],
                encryption=fitz.PDF_ENCRYPT_AES_256,
                owner_pw="owner-secret",
                user_pw="user-secret",
            )
            with self.assertRaisesRegex(ValueError, "mã hóa"):
                extract_pdf_text_pages(str(path))

    def test_pdf_page_limit_is_enforced_before_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.pdf"
            self._make_pdf(path, ["page one", "page two"])
            with self.assertRaisesRegex(ValueError, "vượt giới hạn"):
                extract_pdf_text_pages(str(path), max_pages=1)


class ProcessingRevisionPersistenceTests(unittest.TestCase):
    def test_save_pages_replaces_only_unfinished_revision_and_preserves_empty_raw(self):
        document_id = ObjectId()
        job_id = ObjectId()
        revision_id = ObjectId()
        database = MagicMock()
        database.document_processing_revisions.find_one.return_value = {
            "_id": revision_id,
            "revision_no": 3,
        }
        repository = MongoDocumentRepository(database)
        repository.find_job = MagicMock(
            return_value={
                "_id": job_id,
                "document_id": document_id,
                "document_version": 1,
                "job_type": "OCR",
                "processing_revision_id": revision_id,
                "config": {},
            }
        )

        count = repository.save_pages(
            str(document_id),
            str(job_id),
            [
                {
                    "page_number": 1,
                    "text": "cleaned fallback",
                    "original_text": "",
                    "extraction_method": "TEXT",
                    "quality_flags": [],
                }
            ],
        )

        self.assertEqual(count, 1)
        database.document_pages.delete_many.assert_called_once_with(
            {"processing_revision_id": revision_id}
        )
        saved = database.document_pages.insert_many.call_args.args[0][0]
        self.assertEqual(saved["raw_text"], "")
        self.assertEqual(saved["cleaned_text"], "cleaned fallback")
        self.assertEqual(saved["processing_revision_id"], revision_id)
        self.assertEqual(saved["revision_no"], 3)


class DurableDocumentJobTests(unittest.TestCase):
    def test_claim_increments_fencing_token_and_sets_lease(self):
        database = MagicMock()
        database.document_jobs.find_one_and_update.return_value = {"_id": ObjectId()}
        repository = MongoDocumentRepository(database)
        repository.claim_job(ObjectId(), "worker-1")

        update = database.document_jobs.find_one_and_update.call_args.args[1]
        self.assertEqual(update["$inc"], {"fencing_token": 1, "run_attempt": 1})
        self.assertEqual(update["$set"]["worker_id"], "worker-1")
        self.assertIn("lease_expires_at", update["$set"])


if __name__ == "__main__":
    unittest.main()
