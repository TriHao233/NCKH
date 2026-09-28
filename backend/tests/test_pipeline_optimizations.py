import asyncio
import json
import os
import time

from core import gpu_coordination
from modules.ocr import pdf_text_extractor
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


def test_gpu_operation_reclaims_stale_lock(tmp_path, monkeypatch):
    lock_path = tmp_path / "gpu-operation.lock"
    lock_path.write_text(
        json.dumps({"token": "dead-owner", "label": "ollama", "pid": 1}),
        encoding="utf-8",
    )
    old_time = time.time() - 10
    os.utime(lock_path, (old_time, old_time))
    monkeypatch.setattr(gpu_coordination.settings, "gpu_coordination_enabled", True)
    monkeypatch.setattr(gpu_coordination.settings, "gpu_lock_path", str(lock_path))
    monkeypatch.setattr(gpu_coordination.settings, "gpu_lock_stale_seconds", 0.05)
    monkeypatch.setattr(gpu_coordination.settings, "gpu_lock_heartbeat_seconds", 0.01)
    monkeypatch.setattr(gpu_coordination.settings, "gpu_lock_timeout_seconds", 0.5)
    monkeypatch.setattr(gpu_coordination.settings, "gpu_lock_poll_seconds", 0.01)

    with gpu_coordination.gpu_operation("embedding"):
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
        assert payload["token"] != "dead-owner"
        assert payload["hostname"]

    assert not lock_path.exists()


def test_gpu_operation_heartbeat_keeps_live_lock_fresh(tmp_path, monkeypatch):
    lock_path = tmp_path / "gpu-operation.lock"
    monkeypatch.setattr(gpu_coordination.settings, "gpu_coordination_enabled", True)
    monkeypatch.setattr(gpu_coordination.settings, "gpu_lock_path", str(lock_path))
    monkeypatch.setattr(gpu_coordination.settings, "gpu_lock_heartbeat_seconds", 0.01)

    with gpu_coordination.gpu_operation("unit-test"):
        initial_mtime = lock_path.stat().st_mtime
        time.sleep(0.15)
        assert lock_path.stat().st_mtime > initial_mtime


def test_cancelled_async_waiter_does_not_leave_orphan_lock(tmp_path, monkeypatch):
    lock_path = tmp_path / "gpu-operation.lock"
    lock_path.write_text(
        json.dumps({"token": "active-owner", "label": "embedding"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(gpu_coordination.settings, "gpu_coordination_enabled", True)
    monkeypatch.setattr(gpu_coordination.settings, "gpu_lock_path", str(lock_path))
    monkeypatch.setattr(gpu_coordination.settings, "gpu_lock_stale_seconds", 60)
    monkeypatch.setattr(gpu_coordination.settings, "gpu_lock_timeout_seconds", 1)
    monkeypatch.setattr(gpu_coordination.settings, "gpu_lock_poll_seconds", 0.01)

    async def exercise_cancellation():
        async def wait_for_lock():
            async with gpu_coordination.async_gpu_operation("ollama"):
                pass

        task = asyncio.create_task(wait_for_lock())
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        lock_path.unlink()
        await asyncio.sleep(0.1)
        assert not lock_path.exists()

    asyncio.run(exercise_cancellation())


def test_embedding_model_releases_cuda_between_ollama_operations(monkeypatch):
    class FakeEmbeddingModel:
        def __init__(self):
            self.device = "cuda:0"
            self.moves = []

        def encode(self, documents, **_kwargs):
            return [[float(index), 1.0] for index, _document in enumerate(documents)]

        def to(self, device):
            self.device = str(device)
            self.moves.append(str(device))
            return self

    model = FakeEmbeddingModel()
    empty_cache_calls = []
    monkeypatch.setattr(chromadb_engine, "_get_embedding_model", lambda: model)
    monkeypatch.setattr(chromadb_engine, "embedding_token_lengths", lambda documents: [4] * len(documents))
    monkeypatch.setattr(chromadb_engine.settings, "gpu_coordination_enabled", False)
    monkeypatch.setattr(chromadb_engine.settings, "embedding_release_gpu_after_use", True)
    monkeypatch.setattr(chromadb_engine.torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(chromadb_engine.torch.cuda, "reset_peak_memory_stats", lambda _device: None)
    monkeypatch.setattr(chromadb_engine.torch.cuda, "max_memory_allocated", lambda _device: 0)
    monkeypatch.setattr(chromadb_engine.torch.cuda, "max_memory_reserved", lambda _device: 0)
    monkeypatch.setattr(chromadb_engine.torch.cuda, "empty_cache", lambda: empty_cache_calls.append(True))

    _, first_metrics = chromadb_engine._encode_documents(["first"])
    assert model.device == "cpu"
    assert first_metrics["device"] == "cuda:0"

    _, second_metrics = chromadb_engine._encode_documents(["second"])
    assert model.device == "cpu"
    assert second_metrics["device"] == "cuda"
    assert model.moves == ["cpu", "cuda", "cpu"]
    assert len(empty_cache_calls) == 2
