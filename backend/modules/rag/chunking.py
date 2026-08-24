import hashlib
import logging
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from typing import Iterable

from bson import ObjectId
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.concurrency import run_in_threadpool
from pymongo import ReturnDocument

from core.bootstrap import SCHEMA_VERSION
from core.config import settings
from core.database import get_database
from core.dependencies import CurrentUser, require_teacher_or_admin
from modules.documents.repository import MongoDocumentRepository, object_id
from modules.documents.service import DocumentService, get_document_service
from modules.dictionary.dictionary import run_dictionary_auto_learning
from modules.dictionary.mongodb import get_active_keywords
from modules.rag.chunking_export import export_chunks_to_file
from modules.rag.chromadb_engine import store_chunks
from modules.rag.mongodb import (
    complete_chunk_set,
    get_document_record,
    iter_document_pages,
    is_document_job_cancelled,
    persist_chunks,
    start_chunk_set,
    update_chunking_status,
)
from modules.rag.schemas import ChunkingStats, DocumentChunkRequest, DocumentChunkResponse

router = APIRouter(prefix=f"{settings.api_prefix}/chunk", tags=["chunking"])
logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)

PAGE_MARKER_PATTERN = re.compile(r"<!--\s*PAGE:(\d+)\s*-->")
CODE_BLOCK_PATTERN = re.compile(r"```[^\n]*\n[\s\S]*?```")
FORMULA_BLOCK_PATTERN = re.compile(r"<FORMULA_BLOCK[\s\S]*?</FORMULA_BLOCK>")
LATEX_BLOCK_PATTERN = re.compile(r"\$\$[\s\S]*?\$\$")
TABLE_BLOCK_PATTERN = re.compile(r"(\|[^\n]+\|\n\|[-:\s|]+\|\n(?:\|[^\n]+\|\n?)+)")
HEADING_PATTERN = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)

TOP_LEVEL_PATTERNS = [
	re.compile(r"^#\s+.+$"),
	re.compile(r"^(CHUONG|CHAPTER|PHAN|BAI)\s+([IVX0-9]+)\b"),
]

SUB_LEVEL_2_PATTERN = re.compile(r"^(I|II|III|IV|V|VI|VII|VIII|IX|X)[\.\s]+", re.IGNORECASE)
SUB_LEVEL_3_PATTERN = re.compile(r"^\d+\.\d+(?:\.\d+)?[\.\s]+")

BIG_O_PATTERN = re.compile(r"\bO\([^)]*\)")
EXAMPLE_PATTERN = re.compile(r"\b(thí dụ|ví dụ|vd)\b", re.IGNORECASE)
EXERCISE_PATTERN = re.compile(r"\b(bài tập|câu hỏi|thực hành|luyện tập|ôn tập)\b", re.IGNORECASE)
DEFINITION_PATTERN = re.compile(r"\b(định nghĩa|khái niệm|là gì)\b", re.IGNORECASE)


# -------------------------------------------------------------
# API: Chunk tài liệu OCR và lưu vào ChromaDB
# -------------------------------------------------------------
@router.post("/document", response_model=DocumentChunkResponse, summary="Chunk OCR document and store to ChromaDB")
async def chunk_document(
    req: DocumentChunkRequest,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    document_service: DocumentService = Depends(get_document_service),
):
    doc = get_document_record(req.document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    try:
        document_service.can_use(req.document_id, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    try:
        result = await run_in_threadpool(
            chunk_document_and_store,
            document_id=req.document_id,
            chunk_size=req.chunk_size,
            chunk_overlap=req.chunk_overlap,
            collection_name=req.collection_name,
            buffer_max_pages=req.buffer_max_pages,
            buffer_max_chars=req.buffer_max_chars,
            max_code_block_lines=req.max_code_block_lines,
            dry_run=req.dry_run,
        )

        if not req.dry_run and result.total_chunks > 0:
            logger.info("Đang kích hoạt tiến trình AI học từ khóa ngầm...")
            background_tasks.add_task(
                run_dictionary_auto_learning,
                document_id=req.document_id,
                course_id="it_fundamentals"
            )

        return result
    except Exception as ex:
        logger.exception("Chunking failed: %s", ex)
        update_chunking_status(req.document_id, status="failed", error_message=str(ex))
        raise HTTPException(status_code=500, detail=str(ex)) from ex


def _chunk_run_config(config: dict) -> dict:
    return {
        "strategy": config.get("strategy") or "recursive",
        "chunk_size": int(config.get("chunk_size") or settings.chunk_size_default),
        "chunk_overlap": int(config.get("chunk_overlap") or settings.chunk_overlap_default),
        "buffer_max_pages": int(config.get("buffer_max_pages") or settings.chunk_buffer_max_pages),
        "buffer_max_chars": int(config.get("buffer_max_chars") or settings.chunk_buffer_max_chars),
        "max_code_block_lines": int(config.get("max_code_block_lines") or settings.max_code_block_lines),
        "dry_run": bool(config.get("dry_run", False)),
        "collection_name": config.get("collection_name") or settings.chromadb_collection_name,
    }


def _empty_chunk_stats() -> ChunkingStats:
    return ChunkingStats(
        original_length=0,
        total_chunks=0,
        junk_removed=0,
        avg_chunk_size=0,
        min_chunk_size=0,
        max_chunk_size=0,
        content_type_distribution={},
    )


def _cancelled_chunk_response(
    document_id: str,
    chunk_job_id: str,
    chunk_set_id: str,
    collection_name: str,
) -> DocumentChunkResponse:
    return DocumentChunkResponse(
        document_id=document_id,
        chunk_job_id=chunk_job_id,
        chunk_set_id=chunk_set_id,
        vector_collection_id=None,
        collection_name=collection_name,
        total_chunks=0,
        stored_chunks=0,
        stats=_empty_chunk_stats(),
    )


def process_chunk_retry_background(
    document_id: str,
    chunk_job_id: str,
    chunk_set_id: str,
    run_config: dict,
) -> None:
    try:
        _process_existing_chunk_set(document_id, chunk_job_id, chunk_set_id, run_config)
    except Exception as exc:
        logger.exception("Chunk retry job %s failed", chunk_job_id)
        update_chunking_status(document_id, status="failed", error_message=str(exc))


def queue_chunk_retry(background_tasks: BackgroundTasks, document_id: str, config: dict) -> dict:
    run_config = _chunk_run_config(config)
    chunk_job_id, chunk_set_id = start_chunk_set(document_id, run_config)
    background_tasks.add_task(
        process_chunk_retry_background,
        document_id=document_id,
        chunk_job_id=chunk_job_id,
        chunk_set_id=chunk_set_id,
        run_config=run_config,
    )
    return {"chunk_job_id": chunk_job_id, "chunk_set_id": chunk_set_id}


def _model_collection_name(collection_name: str) -> str:
    suffix = hashlib.sha256(settings.embedding_model_name.encode("utf-8")).hexdigest()[:8]
    return f"{collection_name}_{suffix}"


def _vector_collection_for_current_model(collection_name: str) -> tuple[dict, str]:
    db = get_database()
    now = utc_now()
    record = db.vector_collections.find_one(
        {"provider": "CHROMA", "collection_name": collection_name, "is_active": True},
        sort=[("created_at", -1)],
    )
    model_name = (record.get("embedding_model") or {}).get("model_name") if record else None
    resolved_collection = collection_name
    if record and model_name != settings.embedding_model_name:
        resolved_collection = _model_collection_name(collection_name)
        record = db.vector_collections.find_one(
            {"provider": "CHROMA", "collection_name": resolved_collection, "is_active": True},
            sort=[("created_at", -1)],
        )
    if record:
        return record, resolved_collection
    record = db.vector_collections.find_one_and_update(
        {"provider": "CHROMA", "collection_name": resolved_collection},
        {
            "$setOnInsert": {
                "_id": ObjectId(),
                "schema_version": SCHEMA_VERSION,
                "persist_uri": settings.chromadb_path,
                "embedding_model": {
                    "provider": "SENTENCE_TRANSFORMERS",
                    "model_name": settings.embedding_model_name,
                    "normalize_embeddings": True,
                },
                "distance_metric": "COSINE",
                "is_active": True,
                "created_at": now,
                "retired_at": None,
            }
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return record, resolved_collection


def _heading_path_text(path: list | None) -> str:
    return " > ".join(str(item) for item in (path or []) if item)


def _metadata_for_existing_chunk(chunk: dict, vector_id: ObjectId) -> dict:
    heading = chunk.get("heading") or {}
    heading_path = heading.get("path") or []
    page_range = chunk.get("page_range") or {}
    return {
        "document_id": str(chunk["document_id"]),
        "chunk_id": str(chunk["_id"]),
        "chunk_set_id": str(chunk["chunk_set_id"]),
        "vector_collection_id": str(vector_id),
        "content_hash": chunk.get("content_hash"),
        "heading": heading.get("title") or "",
        "heading_path": heading_path,
        "heading_path_text": _heading_path_text(heading_path),
        "heading_norm": heading.get("normalized") or "",
        "page_start": page_range.get("start"),
        "page_end": page_range.get("end"),
        "page_marks": page_range.get("pages") or [],
        "content_type": chunk.get("content_type", "text"),
        "semantic_type": chunk.get("semantic_type", "theory"),
        "information_density": chunk.get("information_density", 0),
        "token_count": chunk.get("token_count", 0),
    }


def _reindex_payload(chunks: list[dict], vector: dict) -> tuple[list[str], list[str], list[dict], list[ObjectId]]:
    db = get_database()
    now = utc_now()
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict] = []
    embedding_ids: list[ObjectId] = []
    for chunk in chunks:
        external_id = f"{chunk['_id']}:{vector['_id']}"
        embedding = db.chunk_embeddings.find_one_and_update(
            {
                "chunk_id": chunk["_id"],
                "chunk_set_id": chunk["chunk_set_id"],
                "vector_collection_id": vector["_id"],
            },
            {
                "$setOnInsert": {
                    "_id": ObjectId(),
                    "schema_version": SCHEMA_VERSION,
                    "chunk_id": chunk["_id"],
                    "chunk_set_id": chunk["chunk_set_id"],
                    "vector_collection_id": vector["_id"],
                    "external_vector_id": external_id,
                    "chunk_content_hash": chunk.get("content_hash"),
                    "created_at": now,
                },
                "$set": {
                    "status": "PENDING",
                    "embedding_content_hash": None,
                    "error": None,
                    "updated_at": now,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        ids.append(embedding.get("external_vector_id") or external_id)
        documents.append(chunk.get("content", ""))
        metadatas.append(_metadata_for_existing_chunk(chunk, vector["_id"]))
        embedding_ids.append(embedding["_id"])
    return ids, documents, metadatas, embedding_ids


def _mark_embeddings_cancelled(embedding_ids: list[ObjectId], message: str = "Index job cancelled") -> None:
    if not embedding_ids:
        return
    get_database().chunk_embeddings.update_many(
        {"_id": {"$in": embedding_ids}, "status": "PENDING"},
        {
            "$set": {
                "status": "CANCELLED",
                "error": {"message": message, "at": utc_now()},
                "updated_at": utc_now(),
            }
        },
    )


def process_document_reindex_background(
    document_id: str,
    index_job_id: str,
    collection_name: str,
) -> None:
    repository = MongoDocumentRepository(get_database())
    try:
        document = repository.find_by_id(document_id)
        if not document:
            raise ValueError("Không tìm thấy tài liệu")
        chunk_set_id = (document.get("current_processing") or {}).get("chunk_set_id")
        if not chunk_set_id:
            raise ValueError("Tài liệu chưa có chunk set để re-index")
        if is_document_job_cancelled(index_job_id):
            return
        repository.update_job(index_job_id, "PROCESSING", progress=5)
        chunks = list(
            get_database().document_chunks.find(
                {
                    "document_id": document["_id"],
                    "chunk_set_id": object_id(chunk_set_id, "chunk_set_id"),
                }
            ).sort("chunk_no", 1)
        )
        if not chunks:
            raise ValueError("Chunk set hiện hành chưa có chunks")
        vector, resolved_collection = _vector_collection_for_current_model(collection_name)
        ids, documents, metadatas, embedding_ids = _reindex_payload(chunks, vector)
        if is_document_job_cancelled(index_job_id):
            _mark_embeddings_cancelled(embedding_ids)
            return
        stored_chunks = store_chunks(ids, documents, metadatas, resolved_collection)
        now = utc_now()
        if is_document_job_cancelled(index_job_id):
            _mark_embeddings_cancelled(embedding_ids)
            return
        get_database().chunk_embeddings.update_many(
            {"_id": {"$in": embedding_ids}},
            [
                {
                    "$set": {
                        "status": "INDEXED",
                        "embedding_content_hash": "$chunk_content_hash",
                        "indexed_at": now,
                        "updated_at": now,
                        "error": None,
                    }
                }
            ],
        )
        repository.update_job(
            index_job_id,
            "COMPLETED",
            progress=100,
            stats={
                "total_chunks": len(chunks),
                "stored_chunks": stored_chunks,
                "collection_name": resolved_collection,
                "vector_collection_id": str(vector["_id"]),
                "embedding_model_name": settings.embedding_model_name,
            },
        )
        get_database().documents.update_one(
            {"_id": document["_id"], "archived_at": None},
            {
                "$set": {
                    "current_processing.vector_collection_id": vector["_id"],
                    "pipeline_summary.index_status": "COMPLETED",
                    "status": "READY",
                    "updated_at": now,
                }
            },
        )
    except Exception as exc:
        logger.exception("Re-index job %s failed", index_job_id)
        repository.update_job(index_job_id, "FAILED", error_message=str(exc))


def queue_document_reindex(
    background_tasks: BackgroundTasks,
    document_id: str,
    collection_name: str | None = None,
) -> dict:
    resolved_collection = collection_name or settings.chromadb_collection_name
    repository = MongoDocumentRepository(get_database())
    job = repository.create_job(
        document_id,
        "INDEX",
        config={
            "collection_name": resolved_collection,
            "embedding_model_name": settings.embedding_model_name,
        },
    )
    background_tasks.add_task(
        process_document_reindex_background,
        document_id=document_id,
        index_job_id=str(job["_id"]),
        collection_name=resolved_collection,
    )
    return {"index_job_id": str(job["_id"])}


def chunk_document_and_store(
    document_id: str,
    chunk_size: int,
    chunk_overlap: int,
    collection_name: str | None = None,
    buffer_max_pages: int | None = None,
    buffer_max_chars: int | None = None,
    max_code_block_lines: int | None = None,
    dry_run: bool = False,
) -> DocumentChunkResponse:
    doc = get_document_record(document_id)
    if not doc:
        raise ValueError("Không tìm thấy tài liệu")

    run_config = _chunk_run_config(
        {
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "collection_name": collection_name,
            "buffer_max_pages": buffer_max_pages,
            "buffer_max_chars": buffer_max_chars,
            "max_code_block_lines": max_code_block_lines,
            "dry_run": dry_run,
        }
    )
    chunk_job_id, chunk_set_id = start_chunk_set(document_id, run_config)
    return _process_existing_chunk_set(document_id, chunk_job_id, chunk_set_id, run_config)


def _process_existing_chunk_set(
    document_id: str,
    chunk_job_id: str,
    chunk_set_id: str,
    run_config: dict,
) -> DocumentChunkResponse:
    chunk_size = int(run_config["chunk_size"])
    chunk_overlap = int(run_config["chunk_overlap"])
    resolved_buffer_pages = int(run_config["buffer_max_pages"])
    resolved_buffer_chars = int(run_config["buffer_max_chars"])
    resolved_code_lines = int(run_config["max_code_block_lines"])
    resolved_collection = run_config["collection_name"]
    dry_run = bool(run_config.get("dry_run", False))

    if is_document_job_cancelled(chunk_job_id):
        return _cancelled_chunk_response(document_id, chunk_job_id, chunk_set_id, resolved_collection)

    total_chunks = 0
    stored_chunks = 0
    original_length = 0
    total_chars = 0
    min_chunk = None
    max_chunk = 0
    content_type_distribution: Counter[str] = Counter()

    all_chunks_for_export: list[dict] = []
    vector_collection_id: str | None = None

    for buffer_text, source_len in _iter_chapter_buffers(
        document_id,
        resolved_buffer_pages,
        resolved_buffer_chars,
    ):
        if is_document_job_cancelled(chunk_job_id):
            return _cancelled_chunk_response(document_id, chunk_job_id, chunk_set_id, resolved_collection)
        original_length += source_len
        for chunk in _chunk_buffer(
            buffer_text,
            document_id,
            chunk_size,
            chunk_overlap,
            resolved_code_lines,
        ):
            content = chunk["content"]
            metadata = chunk["metadata"]

            # Đẩy vào mảng export
            all_chunks_for_export.append(chunk)

            total_chunks += 1
            char_count = len(content)
            total_chars += char_count
            min_chunk = char_count if min_chunk is None else min(min_chunk, char_count)
            max_chunk = max(max_chunk, char_count)
            content_type_distribution[metadata.get("content_type", "text")] += 1

            if is_document_job_cancelled(chunk_job_id):
                return _cancelled_chunk_response(document_id, chunk_job_id, chunk_set_id, resolved_collection)

    avg_chunk = round(total_chars / max(total_chunks, 1), 2)
    stats = ChunkingStats(
        original_length=original_length,
        total_chunks=total_chunks,
        junk_removed=0,
        avg_chunk_size=avg_chunk,
        min_chunk_size=min_chunk or 0,
        max_chunk_size=max_chunk,
        content_type_distribution=dict(content_type_distribution),
    )

    if is_document_job_cancelled(chunk_job_id):
        return _cancelled_chunk_response(document_id, chunk_job_id, chunk_set_id, resolved_collection)

    if not dry_run and all_chunks_for_export:
        (
            vector_collection_id,
            vector_ids,
            vector_documents,
            vector_metadatas,
        ) = persist_chunks(
            document_id,
            chunk_set_id,
            resolved_collection,
            all_chunks_for_export,
        )
        if is_document_job_cancelled(chunk_job_id):
            return _cancelled_chunk_response(document_id, chunk_job_id, chunk_set_id, resolved_collection)
        stored_chunks = store_chunks(
            vector_ids,
            vector_documents,
            vector_metadatas,
            resolved_collection,
        )

    if is_document_job_cancelled(chunk_job_id):
        return _cancelled_chunk_response(document_id, chunk_job_id, chunk_set_id, resolved_collection)

    complete_chunk_set(
        document_id,
        chunk_job_id,
        chunk_set_id,
        vector_collection_id,
        total_chunks=total_chunks,
        total_characters=total_chars,
        stats=stats.model_dump(),
        dry_run=dry_run,
    )

    # THỰC HIỆN XUẤT FILE SAU KHI ĐÃ CẮT XONG (Bao gồm cả dry_run và real run)
    if all_chunks_for_export:
        try:
            export_chunks_to_file(document_id, all_chunks_for_export)
        except Exception as e:
            logger.error(f"Lỗi khi xuất file metadata: {e}")

    return DocumentChunkResponse(
        document_id=document_id,
        chunk_job_id=chunk_job_id,
        chunk_set_id=chunk_set_id,
        vector_collection_id=vector_collection_id,
        collection_name=resolved_collection,
        total_chunks=total_chunks,
        stored_chunks=stored_chunks,
        stats=stats,
    )


def _iter_chapter_buffers(
	document_id: str,
	buffer_max_pages: int,
	buffer_max_chars: int,
) -> Iterable[tuple[str, int]]:
	buffer_lines: list[str] = []
	buffer_pages = 0
	buffer_chars = 0
	buffer_source_len = 0

	for page in iter_document_pages(document_id):
		page_text = page.get("text", "") or ""
		page_number = page.get("page_number", 0)
		marker = f"<!-- PAGE:{page_number} -->"

		if not buffer_lines:
			buffer_lines.append(marker)
		else:
			buffer_lines.append(marker)

		lines = page_text.splitlines() if page_text else []
		for line in lines:
			normalized_line = _smart_normalize_heading(line)
			if normalized_line.startswith("# "):
				if _buffer_has_content(buffer_lines):
					yield "\n".join(buffer_lines).strip(), buffer_source_len
					buffer_lines = [marker]
					buffer_pages = 0
					buffer_chars = 0
					buffer_source_len = 0

			buffer_lines.append(normalized_line)
			buffer_chars += len(normalized_line) + 1

		buffer_pages += 1
		buffer_source_len += len(page_text)

		if buffer_pages >= buffer_max_pages or buffer_chars >= buffer_max_chars:
			yield "\n".join(buffer_lines).strip(), buffer_source_len
			buffer_lines = []
			buffer_pages = 0
			buffer_chars = 0
			buffer_source_len = 0

	if buffer_lines:
		yield "\n".join(buffer_lines).strip(), buffer_source_len


def _chunk_buffer(
	text: str,
	document_id: str,
	chunk_size: int,
	chunk_overlap: int,
	max_code_block_lines: int,
) -> Iterable[dict]:
	sections = _split_by_markdown_headers(text)
	chunk_index = 0

	# LẤY TỪ KHÓA ĐỘNG TỪ MONGODB (Chỉ gọi 1 lần cho cả Buffer giúp tối ưu performance)
	dynamic_keywords = get_active_keywords(course_id="it_fundamentals")

	for section in sections:
		masked_text, protected = _mask_blocks(section["content"], max_code_block_lines)
		parts = _split_recursive(masked_text, chunk_size, chunk_overlap)

		for part in parts:
			restored = _restore_blocks(part, protected)
			page_marks = _extract_page_marks(restored)
			clean_text = _strip_page_markers(restored)
			if not clean_text.strip():
				continue

			chunk_index += 1
			token_count = _count_tokens(clean_text)

			# TRUYỀN TỪ KHÓA ĐỘNG VÀO HÀM TÍNH DENSITY
			keyword_hits, density = _information_density(clean_text, token_count, dynamic_keywords)
			semantic = _detect_semantic_type(clean_text, section["heading"])
			heading_path_text = " > ".join(section["heading_path"]) if section["heading_path"] else ""
			heading_norm = _normalize_heading_meta(section["heading"]) if section["heading"] else ""
			heading_path_norm = _normalize_heading_meta(heading_path_text) if heading_path_text else ""

			metadata = {
				"document_id": document_id,
				"heading_path": section["heading_path"],
				"heading": section["heading"],
				"heading_path_text": heading_path_text,
				"heading_norm": heading_norm,
				"heading_path_norm": heading_path_norm,
				"page_start": page_marks["page_start"],
				"page_end": page_marks["page_end"],
				"page_marks": page_marks["pages"],
				"content_type": _detect_content_type(clean_text),
				"semantic_type": semantic,
				"keyword_hits": keyword_hits,
				"information_density": density,
				"token_count": token_count,
			}

			chunk_id = _generate_chunk_id(document_id, chunk_index, clean_text)
			yield {
				"chunk_id": chunk_id,
				"content": clean_text,
				"metadata": metadata,
			}


def _split_by_markdown_headers(text: str) -> list[dict]:
	matches = list(HEADING_PATTERN.finditer(text))
	if not matches:
		return [{"heading": "", "heading_path": [], "content": text}]

	sections: list[dict] = []
	if matches[0].start() > 0:
		pre = text[: matches[0].start()].strip()
		if pre:
			sections.append({"heading": "", "heading_path": [], "content": pre})

	heading_stack: list[str] = []
	for i, match in enumerate(matches):
		level = len(match.group(1))
		heading = match.group(2).strip()

		if level == 1:
			heading_stack = [heading]
		elif level == 2:
			heading_stack = heading_stack[:1] + [heading] if heading_stack else [heading]
		else:
			heading_stack = heading_stack[:2] + [heading] if heading_stack else [heading]

		body_start = match.end()
		body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
		body = text[body_start:body_end].strip()
		content = f"{match.group(0).strip()}\n\n{body}" if body else match.group(0).strip()

		sections.append(
			{
				"heading": heading,
				"heading_path": list(heading_stack),
				"content": content,
			}
		)

	return sections


def _strip_accents(text: str) -> str:
	normalized = unicodedata.normalize("NFKD", text)
	return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _normalize_heading_meta(value: str) -> str:
	if not value:
		return ""
	folded = _strip_accents(value)
	return re.sub(r"\s+", " ", folded).strip().lower()


def _is_heading_like_remainder(remainder: str) -> bool:
	"""Real Roman-numeral headings in this corpus are followed by ALL-CAPS
	Vietnamese text (e.g. "I TỪ BÀI TOÁN ĐẾN CHƯƠNG TRÌNH"). Single-letter
	numerals (I/V/X) also collide with common variable names in code/math
	sentences (e.g. "x giống như x = X + 1"), which are lowercase/mixed-case.
	Require the remainder to be substantially uppercase to reject those."""
	letters = [ch for ch in _strip_accents(remainder) if ch.isalpha()]
	if len(letters) < 3:
		return False
	return all(ch.isupper() for ch in letters)


def _smart_normalize_heading(line: str) -> str:
	stripped = line.strip()
	if not stripped:
		return stripped
	if stripped.startswith("#"):
		return stripped
	if len(stripped) > 100:
		return stripped

	folded = _strip_accents(stripped).upper()
	if any(pattern.match(folded) for pattern in TOP_LEVEL_PATTERNS):
		return f"# {stripped}"
	sub2_match = SUB_LEVEL_2_PATTERN.match(stripped)
	if sub2_match and _is_heading_like_remainder(stripped[sub2_match.end():]):
		return f"## {stripped}"
	if SUB_LEVEL_3_PATTERN.match(stripped):
		return f"### {stripped}"

	return stripped


def _buffer_has_content(lines: list[str]) -> bool:
	"""A buffer only counts as real content once it has body text, not just
	page markers or heading lines. Without this, a run of consecutive
	headings (e.g. a table-of-contents page listing every chapter title)
	each triggers a yield, producing near-empty chunks."""
	for line in lines:
		s = line.strip()
		if not s or PAGE_MARKER_PATTERN.match(s):
			continue
		if s.startswith("#"):
			continue
		return True
	return False


def _mask_blocks(text: str, max_code_block_lines: int) -> tuple[str, dict]:
	protected: dict[str, str] = {}
	counter = 0

	def _store(prefix: str, value: str) -> str:
		nonlocal counter
		key = f"__{prefix}_{counter}__"
		protected[key] = value
		counter += 1
		return key

	def _split_code_block(block: str) -> str:
		lines = block.splitlines()
		if len(lines) < 2:
			return _store("CODEBLOCK", block)

		fence = lines[0]
		lang = fence.replace("```", "").strip() or "cpp"
		code_lines = lines[1:-1]
		if len(code_lines) <= max_code_block_lines:
			return _store("CODEBLOCK", block)

		segments = []
		total = (len(code_lines) + max_code_block_lines - 1) // max_code_block_lines
		for idx in range(total):
			start = idx * max_code_block_lines
			end = min(start + max_code_block_lines, len(code_lines))
			seg_lines = code_lines[start:end]
			if idx > 0:
				seg_lines = ["// (Continuation of previous code block)"] + seg_lines
			if idx < total - 1:
				seg_lines = seg_lines + ["// (Continues in next code block)"]
			seg_block = f"```{lang}\n" + "\n".join(seg_lines) + "\n```"
			segments.append(_store("CODEBLOCK", seg_block))

		return "\n\n".join(segments)

	def _replace_code(match: re.Match) -> str:
		return _split_code_block(match.group())

	text = CODE_BLOCK_PATTERN.sub(_replace_code, text)
	text = FORMULA_BLOCK_PATTERN.sub(lambda m: _store("FORMULA", m.group()), text)
	text = LATEX_BLOCK_PATTERN.sub(lambda m: _store("LATEX", m.group()), text)
	text = TABLE_BLOCK_PATTERN.sub(lambda m: _store("TABLE", m.group()), text)

	return text, protected


def _restore_blocks(text: str, protected: dict) -> str:
	for key, value in protected.items():
		text = text.replace(key, value)
	return text


def _split_recursive(
	text: str,
	chunk_size: int,
	chunk_overlap: int,
	separators: list[str] | None = None,
) -> list[str]:
	if separators is None:
		separators = ["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ", ""]

	sep = separators[-1]
	rest = []
	for i, s in enumerate(separators):
		if s == "":
			sep = s
			break
		if s in text:
			sep = s
			rest = separators[i + 1 :]
			break

	splits = text.split(sep) if sep else list(text)
	final: list[str] = []
	good: list[str] = []
	for part in splits:
		if len(part) < chunk_size:
			good.append(part)
		else:
			if good:
				final.extend(_merge(good, sep, chunk_size, chunk_overlap))
				good = []
			if not rest:
				final.append(part)
			else:
				final.extend(_split_recursive(part, chunk_size, chunk_overlap, rest))

	if good:
		final.extend(_merge(good, sep, chunk_size, chunk_overlap))

	return final


def _merge(splits: list[str], sep: str, chunk_size: int, chunk_overlap: int) -> list[str]:
	chunks: list[str] = []
	parts: list[str] = []
	cur_len = 0

	for part in splits:
		test = cur_len + len(part) + (len(sep) if parts else 0)
		if test > chunk_size and parts:
			t = sep.join(parts).strip()
			if t:
				chunks.append(t)
			while cur_len > chunk_overlap and len(parts) > 1:
				cur_len -= len(parts.pop(0)) + len(sep)

		parts.append(part)
		cur_len = sum(len(p) for p in parts) + len(sep) * (len(parts) - 1)

	if parts:
		t = sep.join(parts).strip()
		if t:
			chunks.append(t)

	return chunks


def _extract_page_marks(text: str) -> dict:
	pages = [int(m.group(1)) for m in PAGE_MARKER_PATTERN.finditer(text)]
	if pages:
		return {"pages": sorted(set(pages)), "page_start": min(pages), "page_end": max(pages)}
	return {"pages": [], "page_start": None, "page_end": None}


def _strip_page_markers(text: str) -> str:
	cleaned = PAGE_MARKER_PATTERN.sub("", text)
	cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
	return cleaned.strip()


def _generate_chunk_id(doc_id: str, index: int, content: str) -> str:
	raw = f"{doc_id}::{index}::{content}"
	return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _detect_content_type(text: str) -> str:
	has_code = "```" in text
	has_formula = "<FORMULA_BLOCK" in text or "$$" in text
	if has_code and has_formula:
		return "mixed"
	if has_code:
		return "code"
	if has_formula:
		return "formula"
	return "text"


def _detect_semantic_type(text: str, heading: str) -> str:
	context_to_check = f"{heading} {text[:200]}".strip().lower()
	if EXERCISE_PATTERN.search(context_to_check):
		return "exercise"
	if EXAMPLE_PATTERN.search(context_to_check):
		return "example"
	if DEFINITION_PATTERN.search(context_to_check):
		return "definition"
	return "theory"


def _count_tokens(text: str) -> int:
	return len(re.findall(r"[^\W_]+", text, flags=re.UNICODE))


def _information_density(text: str, token_count: int, keywords: list[str]) -> tuple[int, float]:
	lowered = text.lower()
	hits = 0
	for kw in keywords:
		hits += len(re.findall(rf"\b{re.escape(kw)}\b", lowered))
	hits += len(BIG_O_PATTERN.findall(text))
	density = round(hits / max(token_count, 1), 4)
	return hits, density
