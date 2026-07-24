import hashlib
import json
from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument

from core.bootstrap import SCHEMA_VERSION
from core.config import settings
from core.database import get_database, mongo_transaction
from modules.documents.repository import MongoDocumentRepository, object_id


def utc_now():
    return datetime.now(timezone.utc)


def stable_hash(value) -> str:
    payload = value if isinstance(value, str) else json.dumps(value, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_document_record(doc_id: str) -> dict | None:
    return MongoDocumentRepository(get_database()).find_by_id(doc_id)


def iter_document_pages(doc_id: str):
    document = get_document_record(doc_id)
    if not document:
        return
    ocr_job_id = (document.get("current_processing") or {}).get("ocr_job_id")
    if not ocr_job_id:
        return
    cursor = get_database().document_pages.find(
        {"document_id": document["_id"], "ocr_job_id": ocr_job_id}
    ).sort("page_number", 1)
    for page in cursor:
        yield {
            "page_number": int(page.get("page_number", 0)),
            "text": page.get("cleaned_text", ""),
        }


def start_chunk_set(document_id: str, config: dict) -> tuple[str, str]:
    repository = MongoDocumentRepository(get_database())
    document = repository.find_by_id(document_id)
    if not document:
        raise ValueError("Không tìm thấy tài liệu")
    source_ocr_job_id = (document.get("current_processing") or {}).get("ocr_job_id")
    if not source_ocr_job_id:
        raise ValueError("Tài liệu chưa có OCR job hoàn tất")
    job = repository.create_job(document_id, "CHUNK", config=config)
    repository.update_job(str(job["_id"]), "PROCESSING", progress=1)
    if config.get("dry_run"):
        get_database().documents.update_one(
            {"_id": document["_id"]},
            {
                "$set": {
                    "status": document["status"],
                    "pipeline_summary.chunk_status": (
                        document.get("pipeline_summary") or {}
                    ).get("chunk_status", "NOT_STARTED"),
                }
            },
        )
    now = utc_now()
    chunk_set = {
        "_id": ObjectId(),
        "schema_version": SCHEMA_VERSION,
        "document_id": document["_id"],
        "document_version": document["current_version"],
        "source_ocr_job_id": source_ocr_job_id,
        "chunk_job_id": job["_id"],
        "strategy": config.get("strategy", "recursive"),
        "config": config,
        "config_hash": stable_hash(config),
        "status": "PROCESSING",
        "total_chunks": 0,
        "total_characters": 0,
        "created_at": now,
        "completed_at": None,
        "error": None,
    }
    get_database().chunk_sets.insert_one(chunk_set)
    return str(job["_id"]), str(chunk_set["_id"])


def persist_chunks(
    document_id: str,
    chunk_set_id: str,
    collection_name: str,
    chunks: list[dict],
) -> tuple[str, list[str], list[str], list[dict]]:
    db = get_database()
    document_oid = object_id(document_id, "document_id")
    set_oid = object_id(chunk_set_id, "chunk_set_id")
    now = utc_now()
    records = []
    for index, chunk in enumerate(chunks, start=1):
        metadata = chunk["metadata"]
        content_hash = stable_hash(chunk["content"])
        records.append(
            {
                "_id": ObjectId(),
                "schema_version": SCHEMA_VERSION,
                "document_id": document_oid,
                "chunk_set_id": set_oid,
                "chunk_no": index,
                "content": chunk["content"],
                "content_hash": content_hash,
                "heading": {
                    "title": metadata.get("heading"),
                    "path": metadata.get("heading_path", []),
                    "normalized": metadata.get("heading_norm", ""),
                },
                "page_range": {
                    "start": metadata.get("page_start"),
                    "end": metadata.get("page_end"),
                    "pages": metadata.get("page_marks", []),
                },
                "content_type": metadata.get("content_type", "text"),
                "semantic_type": metadata.get("semantic_type", "theory"),
                "information_density": metadata.get("information_density", 0),
                "token_count": metadata.get("token_count", 0),
                "created_at": now,
            }
        )
    vector = db.vector_collections.find_one_and_update(
        {"provider": "CHROMA", "collection_name": collection_name},
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
    indexed_model = (vector.get("embedding_model") or {}).get("model_name")
    if indexed_model != settings.embedding_model_name:
        raise ValueError(
            "Collection ChromaDB đã dùng embedding model "
            f"'{indexed_model}'. Hãy chọn collection_name mới cho model "
            f"'{settings.embedding_model_name}'."
        )
    if records:
        db.document_chunks.insert_many(records, ordered=True)

    ids, documents, metadatas, embeddings = [], [], [], []
    for chunk, record in zip(chunks, records):
        external_id = f"{record['_id']}:{vector['_id']}"
        metadata = {
            **chunk["metadata"],
            "document_id": document_id,
            "chunk_id": str(record["_id"]),
            "chunk_set_id": chunk_set_id,
            "vector_collection_id": str(vector["_id"]),
            "content_hash": record["content_hash"],
        }
        ids.append(external_id)
        documents.append(chunk["content"])
        metadatas.append(metadata)
        embeddings.append(
            {
                "schema_version": SCHEMA_VERSION,
                "chunk_id": record["_id"],
                "chunk_set_id": set_oid,
                "vector_collection_id": vector["_id"],
                "external_vector_id": external_id,
                "chunk_content_hash": record["content_hash"],
                "embedding_content_hash": None,
                "status": "PENDING",
                "indexed_at": None,
                "error": None,
                "created_at": now,
                "updated_at": now,
            }
        )
    if embeddings:
        db.chunk_embeddings.insert_many(embeddings, ordered=True)
    return str(vector["_id"]), ids, documents, metadatas


def complete_chunk_set(
    document_id: str,
    chunk_job_id: str,
    chunk_set_id: str,
    vector_collection_id: str | None,
    *,
    total_chunks: int,
    total_characters: int,
    stats: dict,
    dry_run: bool,
) -> None:
    db = get_database()
    document_oid = object_id(document_id)
    job_oid = object_id(chunk_job_id)
    set_oid = object_id(chunk_set_id)
    vector_oid = object_id(vector_collection_id) if vector_collection_id else None
    now = utc_now()
    with mongo_transaction() as session:
        db.chunk_sets.update_one(
            {"_id": set_oid},
            {
                "$set": {
                    "status": "DRY_RUN" if dry_run else "COMPLETED",
                    "total_chunks": total_chunks,
                    "total_characters": total_characters,
                    "completed_at": now,
                }
            },
            session=session,
        )
        if vector_oid:
            db.chunk_embeddings.update_many(
                {"chunk_set_id": set_oid, "vector_collection_id": vector_oid},
                [
                    {
                        "$set": {
                            "status": "INDEXED",
                            "embedding_content_hash": "$chunk_content_hash",
                            "indexed_at": now,
                            "updated_at": now,
                        }
                    }
                ],
                session=session,
            )
        db.document_jobs.update_one(
            {"_id": job_oid},
            {
                "$set": {
                    "status": "COMPLETED",
                    "progress": 100,
                    "stats": stats,
                    "finished_at": now,
                }
            },
            session=session,
        )
        document_fields = {"updated_at": now}
        if not dry_run:
            document_fields.update(
                {
                    "pipeline_summary.chunk_status": "COMPLETED",
                    "pipeline_summary.total_chunks": total_chunks,
                    "current_processing.chunk_set_id": set_oid,
                    "current_processing.vector_collection_id": vector_oid,
                    "pipeline_summary.index_status": "COMPLETED",
                    "status": "READY",
                }
            )
        document_result = db.documents.update_one(
            {"_id": document_oid, "archived_at": None},
            {"$set": document_fields},
            session=session,
        )
        if not document_result.matched_count:
            raise RuntimeError("DOCUMENT_ARCHIVED")


def fail_chunk_set(document_id: str, message: str) -> None:
    db = get_database()
    document = db.documents.find_one(
        {"_id": object_id(document_id, "document_id")}
    )
    if not document:
        return
    latest = db.chunk_sets.find_one(
        {"document_id": document["_id"], "status": "PROCESSING"},
        sort=[("created_at", -1)],
    )
    now = utc_now()
    if latest:
        db.chunk_sets.update_one(
            {"_id": latest["_id"]},
            {"$set": {"status": "FAILED", "error": {"message": message, "at": now}, "completed_at": now}},
        )
        db.document_jobs.update_one(
            {"_id": latest["chunk_job_id"]},
            {"$set": {"status": "FAILED", "error": {"message": message, "at": now}, "finished_at": now}},
        )
        db.chunk_embeddings.update_many(
            {"chunk_set_id": latest["_id"], "status": "PENDING"},
            {
                "$set": {
                    "status": "FAILED",
                    "error": {"message": message, "at": now},
                    "updated_at": now,
                }
            },
        )
    db.documents.update_one(
        {"_id": document["_id"], "archived_at": None},
        {
            "$set": {
                "status": "FAILED",
                "pipeline_summary.chunk_status": "FAILED",
                "pipeline_summary.index_status": "FAILED",
                "latest_error": {"message": message, "at": now},
                "updated_at": now,
            }
        },
    )


def update_chunking_status(
    doc_id: str,
    status: str,
    stats: dict | None = None,
    error_message: str | None = None,
    **_kwargs,
):
    """Compatibility entry point used by the API error handler."""
    if status.lower() == "failed":
        fail_chunk_set(doc_id, error_message or "Chunking failed")
