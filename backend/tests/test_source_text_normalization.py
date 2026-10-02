from core.text_normalization import normalize_source_text
from modules.documents.ingest.models import ParseContext
from modules.documents.ingest.parsers.text import TextParser


def test_pdf_artifacts_are_corrected_without_guessing_accents():
    text = "ngƣợc, đƣợc, Ƣu tiên; Cay nhi phan; ký hiệu ƣ."
    expected = "ngược, được, Ưu tiên; Cay nhi phan; ký hiệu ƣ."
    assert normalize_source_text(text) == expected
    assert normalize_source_text(expected) == expected


def test_code_math_and_original_document_text_are_preserved(tmp_path):
    raw = "Văn bản đƣợc đọc. `ngƣợc` $nƣ$\n```python\nnƣ = 1\n```"
    assert normalize_source_text(raw) == raw.replace("đƣợc", "được")
    source = tmp_path / "lesson.txt"
    source.write_text("Văn bản đƣợc đọc.", encoding="utf-8")
    parsed = TextParser().parse(source, ParseContext(
        document_id="test", source_file_name=source.name,
        source_uri=str(source), mime_type="text/plain", document_type="txt",
    ))
    page = parsed.to_page_records()[0]
    assert page["original_text"] == "Văn bản đƣợc đọc."
    assert page["text"] == "Văn bản được đọc."
    assert any(entry["operation"] == "vietnamese_pdf_font_normalization_v1"
               for entry in page["content_blocks"][0]["transformation_log"])
