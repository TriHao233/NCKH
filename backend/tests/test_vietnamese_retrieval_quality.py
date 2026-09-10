from copy import deepcopy
import unicodedata
from unittest.mock import patch

import pytest

from modules.documents.ingest.models import ParseContext
from modules.documents.ingest.parsers.common import make_block
from modules.documents.ingest.parsers.pdf import PdfParser, _blocks_from_text, _looks_like_heading
from modules.rag import chromadb_engine, chunking
from modules.rag.retrieval_policy import filter_retrieval_pages


def source_block(text, kind="prose", page=1, index=0):
    context = ParseContext(document_id="d", source_file_name="technical.pdf", source_uri="technical.pdf",
                           mime_type="application/pdf", document_type="pdf")
    return make_block(context, location_key=f"page:{page}:block:{index}", index=index,
                      block_type=kind, content=text, page_number=page,
                      source_location={"page_number": page, "block_index": index},
                      extractor="pypdf", extraction_method="plain").model_dump(mode="json")


def page(*blocks, number=1):
    return {"page_number": number, "content_blocks": list(blocks)}


def test_filter_cover_toc_and_preserve_actual_chapter_and_originals():
    pages = [
        page(source_block("TRƯỜNG ĐẠI HỌC\nKHOA KỸ THUẬT\nTÊN TÁC GIẢ\nGIÁO TRÌNH\nHỆ THỐNG MẠNG\nTrang 1")),
        page(source_block("MỤC LỤC\nChương 2 Hệ thống mạng ........ 9\n2.1 Giao thức ........ 10", page=2), number=2),
        page(source_block("Chương 2 Hệ thống mạng", "heading", 3),
             source_block("Giao thức quy định cách thức các máy tính trao đổi thông tin với nhau.", page=3, index=1), number=3),
    ]
    original = deepcopy(pages)
    metrics = {}
    result = filter_retrieval_pages(pages, metrics)
    assert pages == original
    assert not result[0]["content_blocks"] and not result[1]["content_blocks"]
    assert result[2]["content_blocks"] == pages[2]["content_blocks"]
    assert metrics["reasons"]["cover_metadata"] == 1
    assert metrics["reasons"]["toc_navigation"] == 1


def test_toc_mixed_with_explanation_does_not_delete_explanation():
    original = source_block("1. Hệ thống ........ 7\nMột hệ thống có nhiều thành phần phối hợp với nhau.")
    result = filter_retrieval_pages([page(original)])[0]["content_blocks"][0]
    assert result["content"] == "Một hệ thống có nhiều thành phần phối hợp với nhau."
    assert result["block_id"] == original["block_id"]
    assert result["transformation_log"][-1]["original_content"] == original["content"]


@pytest.mark.parametrize("kind,text", [
    ("code", 'const char* title = "MỤC LỤC ........ 7";'),
    ("formula", "x = 7"), ("table", "A | B\n1 | 2"), ("table", "Value\n10"),
])
def test_structural_filter_preserves_protected_content(kind, text):
    pages = [page(source_block(text, kind))]
    assert filter_retrieval_pages(pages) == pages


def test_short_real_explanation_not_treated_as_cover():
    pages = [page(source_block("ĐẠI HỌC VÀ MẠNG\nMột mạng kết nối các máy tính.\nDữ liệu được truyền qua kênh."))]
    assert filter_retrieval_pages(pages) == pages


def test_repeated_header_removed_only_at_page_boundary():
    pages = [page(source_block("Giáo trình kỹ thuật\nNội dung bài học.", page=i),
                  source_block("Giáo trình kỹ thuật", "heading", i, 1), number=i) for i in range(1, 5)]
    result = filter_retrieval_pages(pages)
    assert all(p["content_blocks"][0]["content"] == "Nội dung bài học." for p in result)
    assert all(p["content_blocks"][1]["content"] == "Giáo trình kỹ thuật" for p in result)


def test_heading_at_page_end_is_metadata_for_body_not_a_standalone_chunk():
    pages = [page(source_block("CHƯƠNG II", "heading")),
             page(source_block("Đây là nội dung giải thích có ý nghĩa về kỹ thuật xử lý thông tin.", page=2), number=2)]
    with patch.object(chunking, "embedding_token_lengths", side_effect=lambda values: [len(v.split()) for v in values]):
        result = chunking._structured_chunks({"_id": "d", "original_filename": "technical.pdf"}, pages, "d", 300, 20, 50, [], 512)
    assert len(result) == 1
    assert result[0]["metadata"]["heading"] == "CHƯƠNG II"
    assert result[0]["metadata"]["page_marks"] == [2]


def test_consecutive_headings_keep_context_with_body():
    pages = [page(source_block("CHƯƠNG II", "heading"), source_block("XỬ LÝ THÔNG TIN", "heading", index=1),
                  source_block("Một hệ thống xử lý thông tin có các thành phần liên kết với nhau.", index=2))]
    with patch.object(chunking, "embedding_token_lengths", side_effect=lambda values: [len(v.split()) for v in values]):
        result = chunking._structured_chunks({"_id": "d", "original_filename": "technical.pdf"}, pages, "d", 300, 20, 50, [], 512)
    assert len(result) == 1
    assert "CHƯƠNG II / XỬ LÝ THÔNG TIN" == result[0]["metadata"]["heading"]


def test_prose_starting_with_bai_toan_is_not_a_heading():
    assert not _looks_like_heading("Bài toán cần được giải quyết bằng một giải thuật phù hợp.")
    assert _looks_like_heading("2.1 Các thành phần chính")
    assert _looks_like_heading("CHƯƠNG II")
    assert not _looks_like_heading("1987. Giáo trình này cũng được biên soạn dựa trên kinh nghiệm giảng dạy")
    assert not _looks_like_heading("1 a1 HEADER 1")
    assert _looks_like_heading("2.1. Cài đặt cấu trúc:")
    assert not _looks_like_heading("Sau khi xử lý dữ liệu:")


def test_heading_with_definition_label_waits_for_explanatory_body():
    pages = [page(source_block("2. Cấu trúc", "heading"), source_block("Định nghĩa cấu trúc:", index=1)),
             page(source_block("Một cấu trúc tổ chức các thành phần theo những quan hệ được xác định.", page=2), number=2)]
    with patch.object(chunking, "embedding_token_lengths", side_effect=lambda values: [len(v.split()) for v in values]):
        chunks = chunking._structured_chunks({"_id": "d", "original_filename": "technical.pdf"}, pages, "d", 300, 20, 50, [], 512)
    assert len(chunks) == 1
    assert chunks[0]["metadata"]["heading"] == "2. Cấu trúc / Định nghĩa cấu trúc:"


def test_page_footer_is_not_swallowed_by_code_or_hidden_by_later_caption():
    context = ParseContext(document_id="d", source_file_name="x.pdf", source_uri="x.pdf",
                           mime_type="application/pdf", document_type="pdf")
    blocks = _blocks_from_text("void f(){\n  return;\n}\n  Trang 7", context, page_number=7,
                              extractor="pypdf", extraction_method="plain", confidence=1)
    assert blocks[0].block_type == "code"
    assert "Trang" not in blocks[0].content
    records = [b.model_dump(mode="json") for b in blocks]
    records.append(source_block("Hình minh họa", "caption", 7, 100))
    filtered = filter_retrieval_pages([page(*records, number=7)])
    assert "Trang 7" not in "\n".join(b["content"] for b in filtered[0]["content_blocks"])
    assert filtered[0]["content_blocks"][0]["content"] == blocks[0].content


def test_toc_continuations_removed_without_leaking_context():
    pages = [page(source_block("MỤC LỤC\nI. Khái niệm ........ 7\nII. Một tiêu đề dài\ncần xuống dòng ........ 8\nIII. Ứng dụng ........ 9"))]
    assert not filter_retrieval_pages(pages)[0]["content_blocks"]


def test_toc_page_with_actual_explanation_keeps_that_content():
    explanation = "Một giao thức xác định cách thức các thành phần của hệ thống trao đổi thông tin với nhau."
    pages = [page(source_block("MỤC LỤC\nI. Khái niệm ........ 7\nII. Triển khai ........ 8\nIII. Ứng dụng ........ 9\n" + explanation))]
    assert filter_retrieval_pages(pages)[0]["content_blocks"][0]["content"] == explanation


def test_short_explanation_on_navigation_page_is_not_removed():
    text = "MỤC LỤC\nI. Khái niệm ........ 7\nII. Triển khai ........ 8\nIII. Ứng dụng ........ 9\nMột mạng kết nối máy tính."
    result = filter_retrieval_pages([page(source_block(text))])
    assert result[0]["content_blocks"][0]["content"] == "Một mạng kết nối máy tính."


def test_preface_with_technical_protected_content_is_not_wholesale_filtered():
    pages = [page(source_block("LỜI NÓI ĐẦU", "heading"), source_block("x = y + z", "formula", index=1))]
    assert filter_retrieval_pages(pages) == pages


def test_preface_filtered_but_later_matching_heading_not_removed():
    pages = [page(source_block("LỜI NÓI ĐẦU", "heading"), source_block("Cuốn giáo trình được biên soạn bởi các tác giả.", index=1)),
             page(source_block("Nội dung kỹ thuật giải thích cách thức các thành phần xử lý và trao đổi thông tin trong một hệ thống thực tế.", page=2), number=2),
             page(source_block("LỜI NÓI ĐẦU", "heading", 3), source_block("Ví dụ về phần dẫn nhập của một định dạng văn bản.", page=3, index=1), number=3)]
    filtered = filter_retrieval_pages(pages)
    assert not filtered[0]["content_blocks"]
    assert filtered[2]["content_blocks"] == pages[2]["content_blocks"]


def test_recursive_split_keeps_punctuation_and_unicode_words():
    value = "Một cấu trúc dữ liệu. Đường truyền thông tin! Kết nối được duy trì?"
    pieces = chunking._split_recursive(value, 25, 0)
    assert " ".join(pieces) == value
    for piece in pieces:
        assert all(word.strip(".!?") in value.split() or word in value.split() for word in piece.split())
    long_word = unicodedata.normalize("NFD", "nghiêng") * 20
    assert chunking._split_recursive(long_word, 10, 0) == [long_word]


def test_embedding_windows_follow_words_not_subwords_or_combining_marks(monkeypatch):
    monkeypatch.setattr(chunking, "embedding_token_lengths", lambda values: [len(v) + 2 for v in values])
    text = unicodedata.normalize("NFD", "cấu trúc dữ liệu được bảo toàn và truyền qua mạng")
    windows = chunking._embedding_windows(text, "", 25, 0)
    assert " ".join(part for part, _, _ in windows) == text
    assert all(count <= 25 for _, _, count in windows)
    assert all(not unicodedata.combining(part[0]) for part, _, _ in windows)


def test_oversized_single_word_fails_explicitly_instead_of_corrupting_it(monkeypatch):
    monkeypatch.setattr(chunking, "embedding_token_lengths", lambda values: [len(v) for v in values])
    with pytest.raises(ValueError, match="source word"):
        chunking._embedding_windows("a" * 100, "Chương 1", 32, 4)


def test_empty_embedding_input_is_rejected_before_model_load(monkeypatch):
    monkeypatch.setattr(chromadb_engine, "_get_embedding_model", lambda: pytest.fail("must not load model"))
    with pytest.raises(ValueError, match="non-empty"):
        chromadb_engine._encode_documents([" "])


def test_pdf_prefers_unpadded_candidate_and_rejects_pathological_layout(monkeypatch, tmp_path):
    class FakePage:
        def extract_text(self, extraction_mode="plain", space_width=200):
            if extraction_mode == "layout":
                return "Dữ" + " " * 1000 + "liệu\nCấu" + " " * 1000 + "trúc"
            return "Nội dung đầy đủ để sử dụng làm tài liệu kỹ thuật. " * 5 + ("cấu tr úc" if space_width < 2000 else "cấu trúc")

        def get(self, _name, default=None):
            return default

    class Reader:
        is_encrypted = False
        pages = [FakePage()]

    monkeypatch.setattr("modules.documents.ingest.parsers.pdf.PdfReader", lambda *_args, **_kwargs: Reader())
    context = ParseContext(document_id="d", source_file_name="x.pdf", source_uri="x.pdf",
                           mime_type="application/pdf", document_type="pdf")
    parsed = PdfParser(ocr_page_extractor=None).parse(tmp_path / "x.pdf", context)
    assert "cấu trúc" in parsed.units[0].rendered_text()
    assert "cấu tr úc" not in parsed.units[0].rendered_text()
    assert parsed.units[0].raw_extraction["block_candidate"] == "pypdf_plain"
