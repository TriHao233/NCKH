import json

from core import gpu_coordination
from modules.ocr import docling_engine, pdf_text_extractor
from modules.rag import chromadb_engine, chunking


class _FakePage(dict):
    def __init__(self, text: str, *, has_image: bool = False):
        resources = {}
        if has_image:
            resources["/XObject"] = {"image": {"/Subtype": "/Image"}}
        super().__init__({"/Resources": resources})
        self._text = text

    def extract_text(self, **_kwargs):
        return self._text


class _FakeReader:
    is_encrypted = False

    def __init__(self, pages):
        self.pages = pages


def test_pdf_text_fast_path_accepts_dense_text_without_images(monkeypatch):
    pages = [_FakePage("Nội dung tiếng Việt có dấu " * 20) for _ in range(3)]
    monkeypatch.setattr(pdf_text_extractor, "PdfReader", lambda *_args, **_kwargs: _FakeReader(pages))
    monkeypatch.setattr(pdf_text_extractor.settings, "pdf_text_fast_path_min_chars_per_page", 100)
    monkeypatch.setattr(pdf_text_extractor.settings, "pdf_text_fast_path_min_coverage", 1.0)
    monkeypatch.setattr(pdf_text_extractor.settings, "pdf_text_fast_path_max_image_page_ratio", 0.0)

    result = pdf_text_extractor.extract_pdf_text_layer("unused.pdf")

    assert result["eligible"] is True
    assert len(result["pages"]) == 3
    assert result["stats"]["text_coverage"] == 1.0


def test_pdf_text_fast_path_rejects_image_page_before_text_extraction(monkeypatch):
    image_page = _FakePage("text", has_image=True)
    pages = [image_page, _FakePage("text")]
    monkeypatch.setattr(pdf_text_extractor, "PdfReader", lambda *_args, **_kwargs: _FakeReader(pages))
    monkeypatch.setattr(pdf_text_extractor.settings, "pdf_text_fast_path_max_image_page_ratio", 0.0)

    result = pdf_text_extractor.extract_pdf_text_layer("unused.pdf")

    assert result["eligible"] is False
    assert result["pages"] == []
    assert result["stats"]["rejection_reasons"] == ["image_pages_present"]


def test_docling_json_is_reconstructed_with_page_provenance():
    payload = {
        "body": {
            "children": [
                {"$ref": "#/texts/0"},
                {"$ref": "#/texts/1"},
                {"$ref": "#/tables/0"},
            ]
        },
        "texts": [
            {"label": "section_header", "level": 2, "text": "Chương 1", "prov": [{"page_no": 1}]},
            {"label": "text", "text": "Nội dung", "prov": [{"page_no": 1}]},
        ],
        "tables": [
            {
                "label": "table",
                "prov": [{"page_no": 2}],
                "data": {
                    "table_cells": [
                        {"start_row_offset_idx": 0, "end_row_offset_idx": 1, "start_col_offset_idx": 0, "end_col_offset_idx": 1, "text": "A"},
                        {"start_row_offset_idx": 0, "end_row_offset_idx": 1, "start_col_offset_idx": 1, "end_col_offset_idx": 2, "text": "B"},
                        {"start_row_offset_idx": 1, "end_row_offset_idx": 2, "start_col_offset_idx": 0, "end_col_offset_idx": 1, "text": "1"},
                        {"start_row_offset_idx": 1, "end_row_offset_idx": 2, "start_col_offset_idx": 1, "end_col_offset_idx": 2, "text": "2"},
                    ]
                },
            }
        ],
    }

    pages = docling_engine._pages_from_docling_json({"json_content": json.dumps(payload)})

    assert [page["page_number"] for page in pages] == [1, 2]
    assert "## Chương 1" in pages[0]["text"]
    assert "| A | B |" in pages[1]["text"]


def test_docling_text_spanning_pages_is_split_by_provenance_charspan():
    payload = {
        "body": {"children": [{"$ref": "#/texts/0"}]},
        "texts": [{
            "label": "text",
            "text": "Page one Page two",
            "prov": [
                {"page_no": 1, "charspan": [0, 8]},
                {"page_no": 2, "charspan": [9, 17]},
            ],
        }],
    }

    pages = docling_engine._pages_from_docling_json({"json_content": json.dumps(payload)})
    blocks = docling_engine._blocks_from_docling_json({"json_content": json.dumps(payload)})

    assert [(page["page_number"], page["text"]) for page in pages] == [(1, "Page one"), (2, "Page two")]
    assert [(block["page_number"], block["content"]) for block in blocks] == [(1, "Page one"), (2, "Page two")]


def test_docling_rapidocr_custom_backend_does_not_mix_preset_fields(monkeypatch):
    monkeypatch.setattr(docling_engine.settings, "docling_ocr_preset", "rapidocr")
    monkeypatch.setattr(docling_engine.settings, "docling_ocr_backend", "torch")
    monkeypatch.setattr(docling_engine.settings, "docling_ocr_languages", ["latin"])

    fields, backend = docling_engine._ocr_form_data()

    field_names = [name for name, _value in fields]
    custom_config = json.loads(dict(fields)["ocr_custom_config"])
    assert backend == "torch"
    assert "ocr_preset" not in field_names
    assert custom_config == {"kind": "rapidocr", "backend": "torch", "lang": ["latin"]}


def test_docling_default_backend_uses_validated_preset(monkeypatch):
    monkeypatch.setattr(docling_engine.settings, "docling_ocr_preset", "rapidocr")
    monkeypatch.setattr(docling_engine.settings, "docling_ocr_backend", "onnxruntime")
    monkeypatch.setattr(docling_engine.settings, "docling_ocr_languages", ["vi"])

    fields, backend = docling_engine._ocr_form_data()

    assert backend == "onnxruntime"
    assert ("ocr_preset", "rapidocr") in fields
    assert ("ocr_lang", "vi") in fields
    assert all(name != "ocr_custom_config" for name, _value in fields)


def test_token_batches_respect_size_and_padded_token_budget(monkeypatch):
    monkeypatch.setattr(chromadb_engine.settings, "embedding_batch_size", 4)
    monkeypatch.setattr(chromadb_engine.settings, "embedding_batch_max_tokens", 100)
    lengths = [10, 20, 50, 80]

    batches = chromadb_engine._build_token_batches(lengths)

    assert sorted(index for batch in batches for index in batch) == list(range(len(lengths)))
    assert all(len(batch) <= 4 for batch in batches)
    assert all(len(batch) * max(lengths[index] for index in batch) <= 100 for batch in batches)


def test_embedding_windows_preserve_heading_and_token_limit(monkeypatch):
    def fake_lengths(values):
        return [len(value) for value in values]

    monkeypatch.setattr(chunking, "embedding_token_lengths", fake_lengths)
    monkeypatch.setattr(
        chunking,
        "embedding_token_offsets",
        lambda value: [(index, index + 1) for index in range(len(value))],
    )

    windows = chunking._embedding_windows("a " * 100, "Chương 1", 32, 4)

    assert len(windows) > 1
    assert all(content.startswith("[Chương 1]") for _, content, _ in windows)
    assert all(token_count <= 32 for _, _, token_count in windows)


class _FakeCacheCollection:
    def __init__(self):
        self.vectors = {}
        self.get_calls = []

    def get(self, ids, include):
        self.get_calls.append(list(ids))
        found = [cache_id for cache_id in ids if cache_id in self.vectors]
        return {"ids": found, "embeddings": [self.vectors[cache_id] for cache_id in found]}

    def upsert(self, ids, documents, embeddings, metadatas):
        for cache_id, vector in zip(ids, embeddings):
            self.vectors[cache_id] = vector


class _FakeWriteCollection:
    def __init__(self):
        self.calls = []

    def upsert(self, **kwargs):
        self.calls.append(kwargs)


def test_embedding_cache_avoids_reencoding_unchanged_content(monkeypatch):
    cache = _FakeCacheCollection()
    target = _FakeWriteCollection()
    encode_calls = []

    def fake_encode(documents):
        if not documents:
            return [], {"embedding_ms": 0.0, "inference_calls": 0}
        encode_calls.append(list(documents))
        return [[float(index), 1.0] for index, _ in enumerate(documents)], {
            "embedding_ms": 1.0,
            "inference_calls": 1,
        }

    monkeypatch.setattr(chromadb_engine, "_get_embedding_cache_collection", lambda: cache)
    monkeypatch.setattr(chromadb_engine, "_get_write_collection", lambda _name: target)
    monkeypatch.setattr(chromadb_engine, "_encode_documents", fake_encode)
    monkeypatch.setattr(chromadb_engine, "embedding_config_hash", lambda: "a" * 64)
    monkeypatch.setattr(chromadb_engine.settings, "embedding_cache_enabled", True)

    first_metrics = {}
    chromadb_engine.store_chunks(
        ["1", "2"],
        ["alpha", "beta"],
        [{}, {}],
        "test",
        metrics=first_metrics,
    )
    second_metrics = {}
    chromadb_engine.store_chunks(
        ["3", "4"],
        ["alpha", "beta"],
        [{}, {}],
        "test",
        metrics=second_metrics,
    )

    assert len(encode_calls) == 1
    assert first_metrics["cache_misses"] == 2
    assert second_metrics["cache_hits"] == 2
    assert second_metrics["cache_misses"] == 0


def test_embedding_cache_lookup_respects_chroma_batch_size(monkeypatch):
    cache = _FakeCacheCollection()
    target = _FakeWriteCollection()

    monkeypatch.setattr(chromadb_engine, "_get_embedding_cache_collection", lambda: cache)
    monkeypatch.setattr(chromadb_engine, "_get_write_collection", lambda _name: target)
    monkeypatch.setattr(
        chromadb_engine,
        "_encode_documents",
        lambda documents: (
            [[float(index), 1.0] for index, _document in enumerate(documents)],
            {"embedding_ms": 1.0, "inference_calls": 1},
        ),
    )
    monkeypatch.setattr(chromadb_engine, "embedding_config_hash", lambda: "b" * 64)
    monkeypatch.setattr(chromadb_engine.settings, "embedding_cache_enabled", True)
    monkeypatch.setattr(chromadb_engine.settings, "chromadb_batch_size", 2)

    chromadb_engine.store_chunks(
        [str(index) for index in range(5)],
        [f"document-{index}" for index in range(5)],
        [{} for _ in range(5)],
        "test",
    )

    assert [len(call) for call in cache.get_calls] == [2, 2, 1]


def test_gpu_operation_lock_is_released(tmp_path, monkeypatch):
    lock_path = tmp_path / "gpu-operation.lock"
    monkeypatch.setattr(gpu_coordination.settings, "gpu_coordination_enabled", True)
    monkeypatch.setattr(gpu_coordination.settings, "gpu_lock_path", str(lock_path))

    with gpu_coordination.gpu_operation("unit-test"):
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
        assert payload["label"] == "unit-test"

    assert not lock_path.exists()
