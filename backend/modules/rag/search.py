import json
import hashlib
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


_KEYWORD_STOP_WORDS = {
    "cau", "hoi", "tao", "sinh", "theo", "trong", "ngoai", "cho", "voi",
    "mot", "nhung", "cac", "noi", "dung", "kien", "thuc", "phan", "trinh",
}


def _keyword_tokens(text: str) -> set[str]:
    normalized = _strip_accents(text).lower()
    return {
        token
        for token in re.findall(r"[a-z0-9_]{3,}", normalized)
        if token not in _KEYWORD_STOP_WORDS
    }


def _hybrid_score(doc: str, meta: dict, query_tokens: set[str], vector_rank: int) -> float:
    doc_tokens = _keyword_tokens(f"{_build_heading_label(meta)} {doc}")
    lexical = len(query_tokens & doc_tokens) / max(1, len(query_tokens)) if query_tokens else 0.0
    density = min(1.0, max(0.0, float(meta.get("information_density", 0) or 0)))
    reciprocal_rank = 1.0 / (vector_rank + 1)
    return (0.55 * reciprocal_rank) + (0.40 * lexical) + (0.05 * density)


def _estimated_tokens(text: str) -> int:
    return len(re.findall(r"[^\W_]+|[^\s\w]", text or "", flags=re.UNICODE))


def _candidate_key(document: str, metadata: dict) -> str:
    return str(metadata.get("chunk_id") or hashlib.sha256(document.encode("utf-8")).hexdigest())


def _mongo_lexical_candidates(chunk_set_id: str, normalized_target: str) -> list[tuple[str, dict]]:
    try:
        set_oid = ObjectId(chunk_set_id)
    except Exception as exc:
        raise ValueError("Chunk set hiện hành không hợp lệ") from exc
    query: dict = {"chunk_set_id": set_oid}
    if normalized_target:
        target_pattern = re.escape(normalized_target)
        query["$or"] = [
            {"heading.normalized": {"$regex": target_pattern, "$options": "i"}},
            {"heading.title": {"$regex": target_pattern, "$options": "i"}},
            {"heading.path": {"$regex": target_pattern, "$options": "i"}},
        ]
    cursor = get_rag_db().document_chunks.find(
        query,
        {
            "content": 1,
            "content_hash": 1,
            "heading": 1,
            "page_range": 1,
            "information_density": 1,
            "token_count": 1,
            "token_budget_status": 1,
            "parent_section_id": 1,
            "source_processing_revision_id": 1,
            "source_span": 1,
        },
    ).sort("chunk_no", 1).limit(max(1, settings.retrieval_lexical_candidate_limit))
    candidates = []
    for chunk in cursor:
        heading = chunk.get("heading") or {}
        page_range = chunk.get("page_range") or {}
        metadata = {
            "chunk_id": str(chunk["_id"]),
            "chunk_set_id": chunk_set_id,
            "content_hash": chunk.get("content_hash"),
            "heading": heading.get("title") or "",
            "heading_path": heading.get("path") or [],
            "heading_path_text": " > ".join(heading.get("path") or []),
            "page_start": page_range.get("start"),
            "page_end": page_range.get("end"),
            "information_density": chunk.get("information_density", 0),
            "token_count": chunk.get("token_count", 0),
            "token_budget_status": chunk.get("token_budget_status", "UNKNOWN"),
            "parent_section_id": chunk.get("parent_section_id"),
            "source_processing_revision_id": str(
                chunk.get("source_processing_revision_id") or ""
            ),
            "source_span": chunk.get("source_span") or {},
        }
        if normalized_target and not _heading_matches_target(metadata, normalized_target):
            continue
        content = str(chunk.get("content") or "")
        if content:
            candidates.append((content, metadata))
    return candidates


def _lexical_rank(
    candidates: list[tuple[str, dict]], query_tokens: set[str]
) -> list[tuple[str, dict]]:
    ranked = []
    for document, metadata in candidates:
        document_tokens = _keyword_tokens(f"{_build_heading_label(metadata)} {document}")
        matched = sorted(query_tokens & document_tokens)
        if query_tokens and not matched:
            continue
        coverage = len(matched) / max(1, len(query_tokens)) if query_tokens else 0.0
        density = min(1.0, max(0.0, float(metadata.get("information_density", 0) or 0)))
        score = coverage + (0.05 * density)
        ranked.append(
            (
                document,
                {
                    **metadata,
                    "_lexical_score": score,
                    "_matched_terms": matched,
                },
            )
        )
    ranked.sort(
        key=lambda item: (
            -float(item[1].get("_lexical_score", 0)),
            item[1].get("page_start") or 0,
        )
    )
    return ranked


def _fuse_candidates(
    dense: list[tuple[str, dict]],
    lexical: list[tuple[str, dict]],
    retrieval_mode: str,
) -> list[tuple[str, dict]]:
    fused: dict[str, tuple[str, dict]] = {}
    branches = []
    if retrieval_mode in {"hybrid", "dense"}:
        branches.append(("dense", dense, 0.6 if retrieval_mode == "hybrid" else 1.0))
    if retrieval_mode in {"hybrid", "lexical"}:
        branches.append(("lexical", lexical, 0.4 if retrieval_mode == "hybrid" else 1.0))
    for branch_name, branch, weight in branches:
        for rank, (document, metadata) in enumerate(branch, start=1):
            key = _candidate_key(document, metadata)
            current_document, current = fused.get(key, (document, dict(metadata)))
            current[f"_{branch_name}_rank"] = rank
            current[f"_{branch_name}_score"] = metadata.get(f"_{branch_name}_score")
            current["_matched_terms"] = sorted(
                set(current.get("_matched_terms") or [])
                | set(metadata.get("_matched_terms") or [])
            )
            current["_fusion_score"] = float(current.get("_fusion_score", 0)) + (
                weight / (60 + rank)
            )
            fused[key] = (current_document, current)
    return sorted(
        fused.values(),
        key=lambda item: (
            -float(item[1].get("_fusion_score", 0)),
            item[1].get("page_start") or 0,
        ),
    )


def get_context_snapshot(
    document_id: str,
    collection_name: str,
    target_heading: str = None,
    query_text: str = None,
    min_density: float = 0.0,
    limit: int = 5,
    retrieval_mode: str = "hybrid",
    context_token_budget: int | None = None,
) -> dict:
    """Retrieve independent dense/lexical branches and fuse them without scope fallback."""
    if retrieval_mode not in {"hybrid", "dense", "lexical"}:
        raise ValueError("retrieval_mode phải là hybrid, dense hoặc lexical")
    chunk_set_id, vector_collection_id = _active_vector_snapshot(
        document_id,
        collection_name,
    )
    normalized_target = _normalize_heading_text(target_heading) if target_heading else ""
    semantic_query = " ".join(
        part.strip() for part in (target_heading, query_text) if part and part.strip()
    )
    query_tokens = _keyword_tokens(semantic_query)
    resolved_budget = max(
        128,
        context_token_budget or settings.retrieval_context_token_budget,
    )

    try:
        dense_candidates: list[tuple[str, dict]] = []
        if retrieval_mode in {"hybrid", "dense"}:
            collection = get_collection(collection_name)
            collection_count = int(collection.count())
            if collection_count:
                candidate_limit = max(1, min(max(limit * 6, limit), collection_count))
                where_filter = {
                    "$and": [
                        {"document_id": document_id},
                        {"chunk_set_id": chunk_set_id},
                    ]
                }
                if semantic_query:
                    dense_results = collection.query(
                        query_texts=[semantic_query],
                        where=where_filter,
                        n_results=candidate_limit,
                        include=["documents", "metadatas", "distances"],
                    )
                    raw_docs = (dense_results.get("documents") or [[]])[0] or []
                    raw_metas = (dense_results.get("metadatas") or [[]])[0] or []
                    raw_distances = (dense_results.get("distances") or [[]])[0] or []
                else:
                    dense_results = collection.get(
                        where=where_filter,
                        limit=candidate_limit,
                        include=["documents", "metadatas"],
                    )
                    raw_docs = dense_results.get("documents") or []
                    raw_metas = dense_results.get("metadatas") or []
                    raw_distances = []
                for index, (document, metadata) in enumerate(zip(raw_docs, raw_metas)):
                    if not document or (
                        normalized_target
                        and not _heading_matches_target(metadata, normalized_target)
                    ):
                        continue
                    density = float(metadata.get("information_density", 0) or 0)
                    if density < min_density:
                        continue
                    distance = raw_distances[index] if index < len(raw_distances) else None
                    dense_candidates.append(
                        (
                            document,
                            {
                                **metadata,
                                "_dense_score": (
                                    max(0.0, 1.0 - float(distance))
                                    if distance is not None
                                    else 1.0 / (index + 1)
                                ),
                                "_dense_distance": distance,
                            },
                        )
                    )

        lexical_candidates = []
        if retrieval_mode in {"hybrid", "lexical"}:
            lexical_source = _mongo_lexical_candidates(chunk_set_id, normalized_target)
            lexical_candidates = _lexical_rank(lexical_source, query_tokens)
        fused_candidates = _fuse_candidates(
            dense_candidates,
            lexical_candidates,
            retrieval_mode,
        )
        if not fused_candidates:
            detail = (
                f"không có evidence trong chương/mục '{target_heading}'"
                if target_heading
                else "không có evidence phù hợp với truy vấn"
            )
            raise ValueError(f"INSUFFICIENT_EVIDENCE: {detail}")

        selected_chunks = []
        used_tokens = 0
        skipped_for_budget = 0
        for document, metadata in fused_candidates:
            token_count = int(metadata.get("token_count") or _estimated_tokens(document))
            if selected_chunks and used_tokens + token_count > resolved_budget:
                skipped_for_budget += 1
                continue
            selected_chunks.append((document, metadata, token_count))
            used_tokens += token_count
            if len(selected_chunks) >= max(1, limit):
                break

        assembled_context = []
        retrieval_results = []
        for doc, meta, token_count in selected_chunks:
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
                    "token_count": token_count,
                    "token_budget_status": meta.get("token_budget_status", "UNKNOWN"),
                    "parent_section_id": meta.get("parent_section_id"),
                    "source_processing_revision_id": meta.get("source_processing_revision_id"),
                    "source_span": meta.get("source_span") or {},
                    "fusion_score": round(float(meta.get("_fusion_score", 0) or 0), 6),
                    "dense_rank": meta.get("_dense_rank"),
                    "dense_score": meta.get("_dense_score"),
                    "lexical_rank": meta.get("_lexical_rank"),
                    "lexical_score": meta.get("_lexical_score"),
                    "matched_terms": meta.get("_matched_terms") or [],
                    "heading": heading_label,
                }
            )

        return {
            "context_text": "\n\n---\n\n".join(assembled_context),
            "results": retrieval_results,
            "chunk_set_id": chunk_set_id,
            "vector_collection_id": vector_collection_id,
            "trace": {
                "mode": retrieval_mode,
                "query": semantic_query,
                "target_heading": target_heading,
                "scope": {"document_id": document_id, "chunk_set_id": chunk_set_id},
                "dense_candidates": len(dense_candidates),
                "lexical_candidates": len(lexical_candidates),
                "fused_candidates": len(fused_candidates),
                "selected_count": len(selected_chunks),
                "context_token_budget": resolved_budget,
                "context_tokens": used_tokens,
                "skipped_for_budget": skipped_for_budget,
                "hard_heading_filter": bool(normalized_target),
            },
        }

    except Exception as e:
        logger.error(f"Lỗi khi truy xuất ChromaDB: {e}")
        if str(e).startswith("INSUFFICIENT_EVIDENCE:"):
            raise
        raise ValueError(f"Lỗi truy xuất hệ thống Vector: {str(e)}")


def get_context_for_generation(
    document_id: str,
    collection_name: str,
    target_heading: str = None,
    query_text: str = None,
    min_density: float = 0.0,
    limit: int = 5,
    retrieval_mode: str = "hybrid",
    context_token_budget: int | None = None,
) -> str:
    """Compatibility wrapper for callers that only need the assembled text."""
    return get_context_snapshot(
        document_id=document_id,
        collection_name=collection_name,
        target_heading=target_heading,
        query_text=query_text,
        min_density=min_density,
        limit=limit,
        retrieval_mode=retrieval_mode,
        context_token_budget=context_token_budget,
    )["context_text"]
