import json
import logging
import os
from threading import Lock

# Dự án chỉ dùng backend PyTorch. Nếu môi trường tình cờ có TensorFlow/Keras 3,
# transformers sẽ nạp nhánh TF và lỗi import, nên tắt sẵn trước khi import.
os.environ.setdefault("USE_TF", "0")

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from sentence_transformers import SentenceTransformer

from core.config import resolve_path, settings

logger = logging.getLogger(__name__)

_embedding_model: SentenceTransformer | None = None
_chroma_client: chromadb.ClientAPI | None = None
_model_lock = Lock()
_client_lock = Lock()


class STEmbeddingFunction(EmbeddingFunction):
    def __init__(self, model: SentenceTransformer):
        self._model = model

    def __call__(self, input: Documents) -> Embeddings:
        embeddings = self._model.encode(input, normalize_embeddings=True)
        return embeddings.tolist()


def _get_embedding_model() -> SentenceTransformer:
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model
    with _model_lock:
        if _embedding_model is None:
            logger.info("Loading embedding model: %s", settings.embedding_model_name)
            _embedding_model = SentenceTransformer(settings.embedding_model_name)
    return _embedding_model


def get_chroma_client() -> chromadb.ClientAPI:
    global _chroma_client
    if _chroma_client is not None:
        return _chroma_client
    with _client_lock:
        if _chroma_client is None:
            chroma_path = str(resolve_path(settings.chromadb_path))
            _chroma_client = chromadb.PersistentClient(path=chroma_path)
            logger.info("ChromaDB initialized at %s", chroma_path)
    return _chroma_client


def get_collection(collection_name: str | None = None):
    """Open a collection with the same embedding function used for indexing."""
    return get_chroma_client().get_or_create_collection(
        name=collection_name or settings.chromadb_collection_name,
        embedding_function=STEmbeddingFunction(_get_embedding_model()),
        metadata={"hnsw:space": "cosine"},
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
) -> int:
    if not ids:
        return 0

    resolved_collection = collection_name or settings.chromadb_collection_name
    collection = get_collection(resolved_collection)

    batch_size = max(settings.chromadb_batch_size, 1)
    total = len(ids)
    sanitized = [sanitize_metadata_for_chromadb(m) for m in metadatas]

    for i in range(0, total, batch_size):
        end = min(i + batch_size, total)
        collection.upsert(
            ids=ids[i:end],
            documents=documents[i:end],
            metadatas=sanitized[i:end],
        )

    return total
