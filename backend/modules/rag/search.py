import json
import logging
import re
import unicodedata

from modules.rag.vector_store import get_chroma_client

logger = logging.getLogger(__name__)

def _strip_accents(text: str) -> str:
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


def get_context_for_generation(document_id: str, collection_name: str, target_heading: str = None, min_density: float = 0.0, limit: int = 5) -> str:
    """Truy xuất các chunk từ ChromaDB làm Context cho LLM"""
    client = get_chroma_client()

    collection = client.get_or_create_collection(name=collection_name)

    where_filter = {"document_id": document_id}
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
        filtered_chunks: list[tuple[str, dict]] = []
        for doc, meta in chunks_with_meta:
            if not doc:
                continue
            density = float(meta.get("information_density", 0) or 0)
            if density < min_density:
                continue

            if normalized_target:
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

                if not any(normalized_target in cand for cand in heading_candidates if cand):
                    continue

            filtered_chunks.append((doc, meta))

        if not filtered_chunks:
            raise ValueError("Không tìm thấy đoạn văn nào hợp lệ theo tiêu chí đã chọn.")

        filtered_chunks.sort(
            key=lambda x: (-(x[1].get("information_density") or 0.0), x[1].get("page_start") or 0)
        )
        selected_chunks = filtered_chunks[:limit]

        assembled_context = []
        for doc, meta in selected_chunks:
            heading_label = _build_heading_label(meta)
            heading = f"[{heading_label}]" if heading_label else ""
            assembled_context.append(f"Mục lục: {heading}\nNội dung: {doc}")

        return "\n\n---\n\n".join(assembled_context)

    except Exception as e:
        logger.error(f"Lỗi khi truy xuất ChromaDB: {e}")
        raise ValueError(f"Lỗi truy xuất hệ thống Vector: {str(e)}")
