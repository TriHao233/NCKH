import json
import logging
import re
import unicodedata

from bson import ObjectId

from core.config import settings
from core.database import get_rag_db
from modules.rag.chromadb_engine import get_collection

logger = logging.getLogger(__name__)


def _active_vector_snapshot(document_id: str, collection_name: str) -> tuple[str, str]:
    try:
        document_oid = ObjectId(document_id)
    except Exception as exc:
        raise ValueError("document_id không hợp lệ") from exc

    db = get_rag_db()
    document = db.documents.find_one(
        {"_id": document_oid, "schema_version": 2, "archived_at": None}
    )
    if not document:
        raise ValueError("Không tìm thấy tài liệu")

    current = document.get("current_processing") or {}
    chunk_set_id = current.get("chunk_set_id")
    vector_collection_id = current.get("vector_collection_id")
    if not chunk_set_id or not vector_collection_id:
        raise ValueError("Tài liệu chưa có chunk set đã được index")

    vector = db.vector_collections.find_one(
        {"_id": vector_collection_id, "is_active": True}
    )
    if not vector:
        raise ValueError("Không tìm thấy cấu hình vector hiện hành")
    if vector.get("collection_name") != collection_name:
        raise ValueError(
            f"Tài liệu đang được index trong collection '{vector.get('collection_name')}'"
        )
    indexed_model = (vector.get("embedding_model") or {}).get("model_name")
    if indexed_model != settings.embedding_model_name:
        raise ValueError(
            "Embedding model hiện tại không khớp snapshot đã index: "
            f"'{settings.embedding_model_name}' != '{indexed_model}'"
        )
    return str(chunk_set_id), str(vector_collection_id)

def _strip_accents(text: str) -> str:
    text = (text or "").replace("đ", "d").replace("Đ", "D")
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _normalize_heading_text(text: str) -> str:
    stripped = re.sub(r"^#+\s*", "", (text or "").strip())
    folded = _strip_accents(stripped).lower()
    return re.sub(r"\s+", " ", folded).strip()

def _coerce_heading_path(meta: dict) -> list[str]:
    heading_path = meta.get("heading_path")
    if isinstance(heading_path, list):
        return [str(x) for x in heading_path if x]
    if isinstance(heading_path, str) and heading_path:
        try:
            parsed = json.loads(heading_path)
            if isinstance(parsed, list):
                return [str(x) for x in parsed if x]
        except Exception:
            return [heading_path]
    return []


def _build_heading_label(meta: dict) -> str:
    heading_path_text = meta.get("heading_path_text")
    if isinstance(heading_path_text, str) and heading_path_text.strip():
        return heading_path_text.strip()
    path = _coerce_heading_path(meta)
    if path:
        return " > ".join(path)
    heading = meta.get("heading")
    if isinstance(heading, str) and heading.strip():
        return heading.strip()
    return ""


def _heading_matches_target(meta: dict, normalized_target: str) -> bool:
    if not normalized_target:
        return True
    heading_candidates = []
    heading = meta.get("heading", "") or ""
    if heading:
        heading_candidates.append(_normalize_heading_text(heading))
    heading_path_text = meta.get("heading_path_text", "") or ""
    if heading_path_text:
        heading_candidates.append(_normalize_heading_text(heading_path_text))
    heading_path = _coerce_heading_path(meta)
    if heading_path:
        heading_candidates.append(_normalize_heading_text(" > ".join(heading_path)))
    return any(normalized_target in candidate for candidate in heading_candidates if candidate)


def get_context_snapshot(
    document_id: str,
    collection_name: str,
    target_heading: str = None,
    min_density: float = 0.0,
    limit: int = 5,
) -> dict:
    """Truy xuất các chunk từ ChromaDB làm Context cho LLM"""
    chunk_set_id, vector_collection_id = _active_vector_snapshot(
        document_id,
        collection_name,
    )
    collection = get_collection(collection_name)

    where_filter = {
        "$and": [
            {"document_id": document_id},
            {"chunk_set_id": chunk_set_id},
        ]
    }
    normalized_target = _normalize_heading_text(target_heading) if target_heading else ""

    try:
        if target_heading:
            results = collection.query(
                query_texts=[target_heading],
                where=where_filter,
                n_results=max(limit, 1),
                include=["documents", "metadatas"],
            )
            raw_docs = (results.get("documents") or [[]])[0] or []
            raw_metas = (results.get("metadatas") or [[]])[0] or []
        else:
            initial_limit = max(limit * 4, limit, 1)
            results = collection.get(
                where=where_filter,
                limit=initial_limit,
                include=["documents", "metadatas"],
            )
            raw_docs = results.get("documents") or []
            raw_metas = results.get("metadatas") or []
            seed_text = ""
            if raw_docs and raw_metas:
                seed_pairs = list(zip(raw_docs, raw_metas))
                seed_pairs.sort(
                    key=lambda x: (-(x[1].get("information_density") or 0.0), x[1].get("page_start") or 0)
                )
                seed_doc, seed_meta = seed_pairs[0]
                seed_text = _build_heading_label(seed_meta) or (seed_doc[:500] if seed_doc else "")

            if seed_text:
                query_results = collection.query(
                    query_texts=[seed_text],
                    where=where_filter,
                    n_results=initial_limit,
                    include=["documents", "metadatas"],
                )
                query_docs = (query_results.get("documents") or [[]])[0] or []
                query_metas = (query_results.get("metadatas") or [[]])[0] or []
                if query_docs:
                    raw_docs = query_docs
                    raw_metas = query_metas

        if not raw_docs:
            raise ValueError("Không tìm thấy đoạn văn nào hợp lệ để sinh câu hỏi.")

        chunks_with_meta = list(zip(raw_docs, raw_metas))
        candidate_chunks: list[tuple[str, dict]] = []
        heading_matched_chunks: list[tuple[str, dict]] = []
        for doc, meta in chunks_with_meta:
            if not doc:
                continue
            density = float(meta.get("information_density", 0) or 0)
            if density < min_density:
                continue

            candidate_chunks.append((doc, meta))
            if _heading_matches_target(meta, normalized_target):
                heading_matched_chunks.append((doc, meta))

        filtered_chunks = heading_matched_chunks or candidate_chunks
        if not filtered_chunks:
            raise ValueError("Không tìm thấy đoạn văn nào hợp lệ theo tiêu chí đã chọn.")
        if normalized_target and not heading_matched_chunks:
            logger.info(
                "Không có heading khớp target_heading; dùng kết quả vector query làm fallback."
            )

        filtered_chunks.sort(
            key=lambda x: (-(x[1].get("information_density") or 0.0), x[1].get("page_start") or 0)
        )
        selected_chunks = filtered_chunks[:limit]

        assembled_context = []
        retrieval_results = []
        for doc, meta in selected_chunks:
            heading_label = _build_heading_label(meta)
            heading = f"[{heading_label}]" if heading_label else ""
            assembled_context.append(f"Mục lục: {heading}\nNội dung: {doc}")
            retrieval_results.append(
                {
                    "chunk_id": meta.get("chunk_id"),
                    "chunk_set_id": meta.get("chunk_set_id"),
                    "chunk_content_hash": meta.get("content_hash"),
                    "page_start": meta.get("page_start"),
                    "page_end": meta.get("page_end"),
                    "information_density": meta.get("information_density", 0),
                    "heading": heading_label,
                }
            )

        return {
            "context_text": "\n\n---\n\n".join(assembled_context),
            "results": retrieval_results,
            "chunk_set_id": chunk_set_id,
            "vector_collection_id": vector_collection_id,
        }

    except Exception as e:
        logger.error(f"Lỗi khi truy xuất ChromaDB: {e}")
        raise ValueError(f"Lỗi truy xuất hệ thống Vector: {str(e)}")


def get_context_for_generation(
    document_id: str,
    collection_name: str,
    target_heading: str = None,
    min_density: float = 0.0,
    limit: int = 5,
) -> str:
    """Compatibility wrapper for callers that only need the assembled text."""
    return get_context_snapshot(
        document_id=document_id,
        collection_name=collection_name,
        target_heading=target_heading,
        min_density=min_density,
        limit=limit,
    )["context_text"]
