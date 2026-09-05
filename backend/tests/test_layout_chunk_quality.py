from copy import deepcopy
from unittest.mock import patch

from modules.documents.ingest.models import DocumentUnit, ParseContext
from modules.documents.ingest.parsers.common import make_block
from modules.documents.ingest.parsers.pdf import _append_docling_structured_blocks, _blocks_from_text, _normalize_layout_blocks
from modules.documents.ingest.quality import validate_chunks
from modules.rag.chunking import _merge_small_structured_chunks, _split_protected_block, _structured_chunks


def block(kind, text, index=0, **kwargs):
    return make_block(
        ParseContext(document_id="d", source_file_name="lesson.pdf", source_uri="input.pdf",
                     mime_type="application/pdf", document_type="pdf"),
        location_key=f"page:1:{index}", index=index, block_type=kind, content=text,
        source_location={"page_number": 1, "line_start": index + 1}, page_number=1,
        extractor="pypdf", extraction_method="layout", **kwargs,
    )


def test_normalization_keeps_raw_text_source_identity_and_protected_content():
    rows = [["Header A", "Header B"], ["a  b", "1"], ["c|d", "2"]]
    entries = [
        block("table", "Header A                      Header B\na  b                       1\nc|d                2",
              structured_content={"rows": rows}),
        block("prose", "Dữ liệu                      tiếng Việt", 1),
        block("code", '    x = "a                      b";\n        return x;', 2),
        block("formula", "x                      = y", 3, structured_content={"raw": "x = y"}),
    ]
    unit = DocumentUnit(unit_number=1, page_number=1, raw_text="original", content_blocks=entries)
    before = deepcopy(entries)
    _normalize_layout_blocks([unit])
    assert entries[0].content == "Header A | Header B\na  b | 1\nc\\|d | 2"
    assert entries[0].structured_content["rows"] == rows
    assert entries[1].content == "Dữ liệu tiếng Việt"
    for original, changed in zip(before, entries):
        assert changed.block_id == original.block_id
        assert changed.provenance == original.provenance
    assert unit.raw_text == "original"
    assert entries[2:] == before[2:]
    assert entries[0].transformation_log[-1]["original_content"] == before[0].content
    log = deepcopy(entries[0].transformation_log)
    _normalize_layout_blocks([unit])
    assert entries[0].transformation_log == log  # idempotent


def test_table_bbox_matches_cells_when_renderings_differ_without_duplicate_block():
    table = block("table", "A                    B\n1                    2",
                  structured_content={"rows": [["A", "B"], ["1", "2"]]})
    unit = DocumentUnit(unit_number=1, page_number=1, content_blocks=[table])
    result = {"structured_blocks": [{
        "block_type": "table", "content": "| A | B |\n| --- | --- |\n| 1 | 2 |",
        "structured_content": {"rows": [["A", "B"], ["1", "2"]]}, "bbox": [1, 2, 30, 40],
    }]}
    context = ParseContext(document_id="d", source_file_name="lesson.pdf", source_uri="input.pdf",
                           mime_type="application/pdf", document_type="pdf")
    _append_docling_structured_blocks(unit, result, context, [], page_number=1, confidence=1)
    assert len(unit.content_blocks) == 1
    assert table.provenance.bbox == [1, 2, 30, 40]
    _append_docling_structured_blocks(unit, result, context, [], page_number=1, confidence=1)
    assert len(unit.content_blocks) == 1


def test_bbox_is_not_borrowed_from_a_different_table():
    table = block("table", "A B\n1 2", structured_content={"rows": [["A", "B"], ["1", "2"]]})
    unit = DocumentUnit(unit_number=1, page_number=1, content_blocks=[table])
    context = ParseContext(document_id="d", source_file_name="lesson.pdf", source_uri="input.pdf",
                           mime_type="application/pdf", document_type="pdf")
    _append_docling_structured_blocks(unit, {"structured_blocks": [{
        "block_type": "table", "content": "A B\n9 8",
        "structured_content": {"rows": [["A", "B"], ["9", "8"]]}, "bbox": [1, 2, 30, 40],
    }]}, context, [], page_number=1, confidence=1)
    assert table.provenance.bbox is None
    assert len(unit.content_blocks) == 2


def test_identical_tables_at_different_bboxes_keep_both_source_occurrences():
    table = block("table", "A | B\n1 | 2", structured_content={"rows": [["A", "B"], ["1", "2"]]})
    table.provenance.bbox = [1, 2, 30, 40]
    unit = DocumentUnit(unit_number=1, page_number=1, content_blocks=[table])
    context = ParseContext(document_id="d", source_file_name="lesson.pdf", source_uri="input.pdf",
                           mime_type="application/pdf", document_type="pdf")
    result = {"structured_blocks": [{
        "block_type": "table", "content": "A | B\n1 | 2",
        "structured_content": {"rows": [["A", "B"], ["1", "2"]]}, "bbox": [1, 50, 30, 90],
    }]}
    _append_docling_structured_blocks(unit, result, context, [], page_number=1, confidence=1)
    assert len(unit.content_blocks) == 2
    assert table.provenance.bbox == [1, 2, 30, 40]
    assert unit.content_blocks[1].provenance.bbox == [1, 50, 30, 90]
    _append_docling_structured_blocks(unit, result, context, [], page_number=1, confidence=1)
    assert len(unit.content_blocks) == 2


def test_ragged_justified_prose_is_not_fabricated_into_table_cells():
    text = "Một dòng       có       khoảng trắng\nDòng tiếp theo                 ngắn hơn"
    context = ParseContext(document_id="d", source_file_name="lesson.pdf", source_uri="input.pdf",
                           mime_type="application/pdf", document_type="pdf")
    blocks = _blocks_from_text(text, context, page_number=1, extractor="pypdf",
                              extraction_method="layout", confidence=1)
    assert all(entry.block_type != "table" for entry in blocks)
    assert "\n".join(entry.content for entry in blocks) == text


def chunk(content, page, heading="", continuation=None):
    return {"chunk_id": f"chunk-{page}", "content": content, "metadata": {
        "document_id": "d", "source_uri": "input.pdf", "source_file_name": "lesson.pdf",
        "page_marks": [page], "heading": heading, "continuation_of": continuation,
        "content_type": "text", "block_ids": [f"b-{page}"],
    }}


def test_duplicate_detection_keeps_both_source_pages_and_flags_empty_content():
    chunks = [chunk("Repeated source header", 4), chunk("Repeated source header", 5)]
    before = deepcopy(chunks)
    quality = validate_chunks(chunks)
    assert quality.status == "needs_review"
    assert quality.metrics["duplicate_chunks"] == 1
    assert chunks == before
    assert validate_chunks([chunk("  ", 1)]).status == "quality_failed"
    assert validate_chunks([]).status == "quality_failed"


def test_short_merge_obeys_page_heading_continuation_and_token_budget():
    with patch("modules.rag.chunking.embedding_token_lengths", side_effect=lambda values: [len(v) for v in values]):
        assert len(_merge_small_structured_chunks([chunk("aa", 1), chunk("bb", 1)], "d", 100, [])) == 1
        for second in [chunk("bb", 2), chunk("bb", 1, heading="New"), chunk("bb", 1, continuation="parent")]:
            assert len(_merge_small_structured_chunks([chunk("aa", 1), second], "d", 100, [])) == 2
        assert len(_merge_small_structured_chunks(
            [chunk("aa", 1), chunk("bb", 1)], "d", 100, [], embedding_max_tokens=5,
        )) == 2


def test_structured_chunks_propagate_missing_bbox_without_losing_page_references():
    table = block("table", "A | B\n1 | 2", structured_content={"rows": [["A", "B"], ["1", "2"]]})
    pages = [{"page_number": 1, "content_blocks": [table.model_dump(mode="json")]}]
    with patch("modules.rag.chunking.embedding_token_lengths", side_effect=lambda values: [len(v.split()) for v in values]):
        chunks = _structured_chunks({"_id": "d", "original_filename": "lesson.pdf"}, pages, "d", 100, 10, 20, [], 512)
    assert chunks[0]["metadata"]["requires_review"]
    assert chunks[0]["metadata"]["page_marks"] == [1]
    assert chunks[0]["metadata"]["block_ids"] == [table.block_id]
    assert validate_chunks(chunks).status == "needs_review"


def test_protected_long_row_and_formula_remain_lossless():
    for kind, text in [("table", "a" * 1600 + " | b"), ("formula", "x" * 1600 + " = y")]:
        parts = _split_protected_block({"block_id": "b", "block_type": kind, "content": text}, 1000, 50)
        assert "".join(part["content"] for part in parts) == text
        assert len(parts) == 1
