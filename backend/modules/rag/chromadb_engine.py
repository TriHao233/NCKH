import json
import hashlib
import logging
import os
from time import perf_counter
from threading import Lock

# Dự án chỉ dùng backend PyTorch. Nếu môi trường tình cờ có TensorFlow/Keras 3,
# transformers sẽ nạp nhánh TF và lỗi import, nên tắt sẵn trước khi import.
os.environ.setdefault("USE_TF", "0")

import chromadb
import torch
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer

from core.config import resolve_path, settings
from core.gpu_coordination import gpu_operation

logger = logging.getLogger(__name__)

_embedding_model: SentenceTransformer | None = None
_embedding_tokenizer = None
_chroma_client: chromadb.ClientAPI | None = None
_model_lock = Lock()
_tokenizer_lock = Lock()
_client_lock = Lock()
_model_load_ms = 0.0
_resolved_precision = ""


class STEmbeddingFunction(EmbeddingFunction):
    def __init__(self, model: SentenceTransformer | None = None):
        self._model = model

    def __call__(self, input: Documents) -> Embeddings:
        embeddings, _ = _encode_documents(list(input), model=self._model)
        return embeddings


def _target_precision() -> str:
    requested = settings.embedding_precision
    if requested not in {"auto", "fp32", "fp16", "bf16"}:
        logger.warning("Unsupported EMBEDDING_PRECISION=%s; falling back to auto", requested)
        requested = "auto"
    if requested == "auto":
        return "fp16" if torch.cuda.is_available() else "fp32"
    if requested in {"fp16", "bf16"} and not torch.cuda.is_available():
        logger.warning("%s embedding precision requires CUDA; using FP32 on CPU", requested.upper())
        return "fp32"
    if requested == "bf16" and not torch.cuda.is_bf16_supported():
        logger.warning("BF16 is not supported by this CUDA device; using FP16")
        return "fp16"
    return requested


def embedding_config_snapshot() -> dict:
    return {
        "model_name": settings.embedding_model_name,
        "model_revision": settings.embedding_model_revision or None,
        "precision": _resolved_precision or _target_precision(),
        "normalize_embeddings": True,
    }


def embedding_config_hash() -> str:
    payload = json.dumps(embedding_config_snapshot(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _get_embedding_model() -> SentenceTransformer:
    global _embedding_model, _model_load_ms, _resolved_precision
    if _embedding_model is not None:
        return _embedding_model
    with _model_lock:
        if _embedding_model is None:
            logger.info("Loading embedding model: %s", settings.embedding_model_name)
            started_at = perf_counter()
            model_kwargs = {}
            if settings.embedding_model_revision:
                model_kwargs["revision"] = settings.embedding_model_revision
            _embedding_model = SentenceTransformer(settings.embedding_model_name, **model_kwargs)
            target_precision = _target_precision()
            if target_precision == "fp16":
                _embedding_model.half()
            elif target_precision == "bf16":
                _embedding_model.bfloat16()
            _embedding_model.eval()
            _resolved_precision = target_precision
            _model_load_ms = (perf_counter() - started_at) * 1000
            logger.info(
                "Embedding model ready: device=%s precision=%s load_ms=%.2f",
                _embedding_model.device,
                target_precision,
                _model_load_ms,
            )
    return _embedding_model


def _get_embedding_tokenizer():
    global _embedding_tokenizer
    if _embedding_tokenizer is not None:
        return _embedding_tokenizer
    with _tokenizer_lock:
        if _embedding_tokenizer is None:
            kwargs = {"use_fast": True}
            if settings.embedding_model_revision:
                kwargs["revision"] = settings.embedding_model_revision
            _embedding_tokenizer = AutoTokenizer.from_pretrained(settings.embedding_model_name, **kwargs)
    return _embedding_tokenizer


def embedding_token_lengths(texts: list[str]) -> list[int]:
    if not texts:
        return []
    tokenizer = _get_embedding_tokenizer()
    encoded = tokenizer(
        texts,
        add_special_tokens=True,
        padding=False,
        truncation=False,
        return_length=True,
    )
    lengths = encoded.get("length")
    if lengths is not None:
        return [int(length) for length in lengths]
    return [len(input_ids) for input_ids in encoded["input_ids"]]


def embedding_token_offsets(text: str) -> list[tuple[int, int]]:
    tokenizer = _get_embedding_tokenizer()
    encoded = tokenizer(
        text,
        add_special_tokens=False,
        padding=False,
        truncation=False,
        return_offsets_mapping=True,
    )
    return [(int(start), int(end)) for start, end in encoded.get("offset_mapping", []) if end > start]


def _build_token_batches(lengths: list[int]) -> list[list[int]]:
    max_batch_size = max(settings.embedding_batch_size, 1)
    max_padded_tokens = max(settings.embedding_batch_max_tokens, 1)
    ordered = sorted(range(len(lengths)), key=lambda index: lengths[index])
    batches: list[list[int]] = []
    current: list[int] = []
    current_max = 0

    for index in ordered:
        next_max = max(current_max, max(lengths[index], 1))
        exceeds_size = len(current) >= max_batch_size
        exceeds_tokens = bool(current) and (len(current) + 1) * next_max > max_padded_tokens
        if exceeds_size or exceeds_tokens:
            batches.append(current)
            current = []
            current_max = 0
        current.append(index)
        current_max = max(current_max, max(lengths[index], 1))
    if current:
        batches.append(current)
    return batches


def _encode_documents(
    documents: list[str],
    *,
    model: SentenceTransformer | None = None,
) -> tuple[list[list[float]], dict]:
    if not documents:
        return [], {
            "inference_calls": 0,
            "embedding_ms": 0.0,
            "gpu_lock_wait_ms": 0.0,
            "inference_ms": 0.0,
            "tokenization_ms": 0.0,
            "batch_sizes": [],
            "batch_max_tokens": [],
            "batch_padded_tokens": [],
            "max_input_tokens": 0,
            "avg_input_tokens": 0,
            "peak_allocated_mb": 0.0,
            "peak_reserved_mb": 0.0,
            "model_load_ms": round(_model_load_ms, 2),
            "precision": _resolved_precision or _target_precision(),
            "device": str(_embedding_model.device) if _embedding_model is not None else "cache-only",
        }

    tokenization_started_at = perf_counter()
    if any(not isinstance(document, str) or not document.strip() for document in documents):
        raise ValueError("Embedding input must contain non-empty text")
    lengths = embedding_token_lengths(documents)
    tokenization_ms = (perf_counter() - tokenization_started_at) * 1000
    batches = _build_token_batches(lengths)
    results: list[list[float] | None] = [None] * len(documents)
    embedding_started_at = perf_counter()
    lock_wait_started_at = perf_counter()
    lock_wait_ms = 0.0
    inference_ms = 0.0
    peak_allocated_mb = 0.0
    peak_reserved_mb = 0.0
    with gpu_operation("embedding"):
        lock_wait_ms = (perf_counter() - lock_wait_started_at) * 1000
        resolved_model = model or _get_embedding_model()
        model_device = torch.device(str(resolved_model.device))
        if model_device.type == "cuda":
            torch.cuda.reset_peak_memory_stats(model_device)
        inference_started_at = perf_counter()
        for batch in batches:
            batch_documents = [documents[index] for index in batch]
            encoded = resolved_model.encode(
                batch_documents,
                batch_size=len(batch_documents),
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
            vectors = encoded.tolist() if hasattr(encoded, "tolist") else list(encoded)
            for index, vector in zip(batch, vectors):
                results[index] = [float(value) for value in vector]
        inference_ms = (perf_counter() - inference_started_at) * 1000
        if model_device.type == "cuda":
            peak_allocated_mb = torch.cuda.max_memory_allocated(model_device) / (1024 * 1024)
            peak_reserved_mb = torch.cuda.max_memory_reserved(model_device) / (1024 * 1024)

    embedding_ms = (perf_counter() - embedding_started_at) * 1000
    if any(vector is None for vector in results):
        raise RuntimeError("Embedding model returned an incomplete batch")

    metrics = {
        "tokenization_ms": round(tokenization_ms, 2),
        "embedding_ms": round(embedding_ms, 2),
        "gpu_lock_wait_ms": round(lock_wait_ms, 2),
        "inference_ms": round(inference_ms, 2),
        "inference_calls": len(batches),
        "batch_sizes": [len(batch) for batch in batches],
        "batch_max_tokens": [max(lengths[index] for index in batch) for batch in batches],
        "batch_padded_tokens": [len(batch) * max(lengths[index] for index in batch) for batch in batches],
        "max_input_tokens": max(lengths, default=0),
        "avg_input_tokens": round(sum(lengths) / max(len(lengths), 1), 2),
        "peak_allocated_mb": round(peak_allocated_mb, 2),
        "peak_reserved_mb": round(peak_reserved_mb, 2),
        "model_load_ms": round(_model_load_ms, 2),
        "precision": _resolved_precision or _target_precision(),
        "device": str(resolved_model.device),
    }
    return [vector for vector in results if vector is not None], metrics


def get_chroma_client() -> chromadb.ClientAPI:
    global _chroma_client
    if _chroma_client is not None:
        return _chroma_client
    with _client_lock:
        if _chroma_client is None:
            chroma_path = str(resolve_path(settings.chromadb_path))
            client_settings = chromadb.config.Settings(anonymized_telemetry=False)
            _chroma_client = chromadb.PersistentClient(path=chroma_path, settings=client_settings)
            logger.info("ChromaDB initialized at %s", chroma_path)
    return _chroma_client


def get_collection(collection_name: str | None = None):
    """Open a collection with the same embedding function used for indexing."""
    return get_chroma_client().get_or_create_collection(
        name=collection_name or settings.chromadb_collection_name,
        embedding_function=STEmbeddingFunction(),
        metadata={"hnsw:space": "cosine"},
    )


def _get_write_collection(collection_name: str):
    return get_chroma_client().get_or_create_collection(
        name=collection_name,
        embedding_function=None,
        metadata={"hnsw:space": "cosine"},
    )


def _get_embedding_cache_collection():
    cache_name = f"embedding-cache-{embedding_config_hash()[:16]}"
    return get_chroma_client().get_or_create_collection(
        name=cache_name,
        embedding_function=None,
        metadata={
            "hnsw:space": "cosine",
            "purpose": "embedding-cache",
            "embedding_config_hash": embedding_config_hash(),
        },
    )


def sanitize_metadata_for_chromadb(meta: dict) -> dict:
    cleaned: dict = {}
    for key, value in meta.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            cleaned[key] = value
        else:
            cleaned[key] = json.dumps(value, ensure_ascii=True)
    return cleaned


def store_chunks(
    ids: list[str],
    documents: list[str],
    metadatas: list[dict],
    collection_name: str | None = None,
    metrics: dict | None = None,
) -> int:
    if not ids:
        return 0

    resolved_collection = collection_name or settings.chromadb_collection_name
    started_at = perf_counter()
    collection = _get_write_collection(resolved_collection)

    batch_size = max(settings.chromadb_batch_size, 1)
    total = len(ids)
    config_hash = embedding_config_hash()
    sanitized = [
        sanitize_metadata_for_chromadb({**metadata, "embedding_config_hash": config_hash})
        for metadata in metadatas
    ]

    document_hashes = [hashlib.sha256(document.encode("utf-8")).hexdigest() for document in documents]
    cache_ids = [f"embedding:{config_hash}:{content_hash}" for content_hash in document_hashes]
    unique_documents: dict[str, str] = {}
    cache_content_hashes: dict[str, str] = {}
    for cache_id, content_hash, document in zip(cache_ids, document_hashes, documents):
        unique_documents.setdefault(cache_id, document)
        cache_content_hashes.setdefault(cache_id, content_hash)

    cached_vectors: dict[str, list[float]] = {}
    cache_lookup_ms = 0.0
    cache_collection = None
    if settings.embedding_cache_enabled:
        cache_started_at = perf_counter()
        try:
            cache_collection = _get_embedding_cache_collection()
            unique_cache_ids = list(unique_documents)
            for start in range(0, len(unique_cache_ids), batch_size):
                lookup_ids = unique_cache_ids[start : start + batch_size]
                cache_result = cache_collection.get(ids=lookup_ids, include=["embeddings"])
                returned_ids = cache_result.get("ids") or []
                returned_embeddings = cache_result.get("embeddings")
                if returned_embeddings is not None:
                    for cache_id, vector in zip(returned_ids, returned_embeddings):
                        cached_vectors[cache_id] = [float(value) for value in vector]
        except Exception:
            logger.warning("Embedding cache lookup failed; continuing without cached vectors", exc_info=True)
            cache_collection = None
            cached_vectors = {}
        cache_lookup_ms = (perf_counter() - cache_started_at) * 1000

    missing_ids = [cache_id for cache_id in unique_documents if cache_id not in cached_vectors]
    missing_id_set = set(missing_ids)
    missing_documents = [unique_documents[cache_id] for cache_id in missing_ids]
    new_vectors, encode_metrics = _encode_documents(missing_documents)
    cached_vectors.update(zip(missing_ids, new_vectors))

    cache_write_ms = 0.0
    if cache_collection is not None and missing_ids:
        cache_write_started_at = perf_counter()
        try:
            for start in range(0, len(missing_ids), batch_size):
                end = min(start + batch_size, len(missing_ids))
                cache_collection.upsert(
                    ids=missing_ids[start:end],
                    documents=missing_documents[start:end],
                    embeddings=new_vectors[start:end],
                    metadatas=[
                        {
                            "content_hash": cache_content_hashes[cache_id],
                            "embedding_config_hash": config_hash,
                        }
                        for cache_id in missing_ids[start:end]
                    ],
                )
        except Exception:
            logger.warning("Embedding cache write failed; primary Chroma write will continue", exc_info=True)
        cache_write_ms = (perf_counter() - cache_write_started_at) * 1000

    embeddings = [cached_vectors[cache_id] for cache_id in cache_ids]

    write_started_at = perf_counter()
    for i in range(0, total, batch_size):
        end = min(i + batch_size, total)
        collection.upsert(
            ids=ids[i:end],
            documents=documents[i:end],
            embeddings=embeddings[i:end],
            metadatas=sanitized[i:end],
        )
    chroma_write_ms = (perf_counter() - write_started_at) * 1000

    if metrics is not None:
        metrics.update(encode_metrics)
        metrics.update(
            {
                "cache_enabled": settings.embedding_cache_enabled,
                "cache_hits": total - sum(cache_id in missing_id_set for cache_id in cache_ids),
                "cache_misses": sum(cache_id in missing_id_set for cache_id in cache_ids),
                "unique_cache_entries": len(unique_documents),
                "cache_lookup_ms": round(cache_lookup_ms, 2),
                "cache_write_ms": round(cache_write_ms, 2),
                "chroma_write_ms": round(chroma_write_ms, 2),
                "total_ms": round((perf_counter() - started_at) * 1000, 2),
                "embedding_config_hash": config_hash,
            }
        )

    return total
