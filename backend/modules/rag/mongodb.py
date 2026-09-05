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


def embedding_model_manifest(collection_name: str) -> dict:
    payload = {
        "provider": "SENTENCE_TRANSFORMERS",
        "model_name": settings.embedding_model_name,
        "normalize_embeddings": True,
        "distance_metric": "COSINE",
        "collection_name": collection_name,
    }
    return {**payload, "model_digest": stable_hash(payload)}


def get_document_record(doc_id: str) -> dict | None:
    return MongoDocumentRepository(get_database()).find_by_id(doc_id)


def is_document_job_cancelled(
    job_id: str,
    worker_id: str | None = None,
    fencing_token: int | None = None,
) -> bool:
    job = get_database().document_jobs.find_one(
        {"_id": object_id(job_id, "job_id")},
        {"status": 1, "worker_id": 1, "fencing_token": 1},
    )
    if not job or job.get("status") == "CANCELLED":
        return True
    if worker_id is not None and job.get("worker_id") != worker_id:
        return True
    if fencing_token is not None and job.get("fencing_token") != fencing_token:
        return True
    return False


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
    get_database().documents.update_one(
        {"_id": document["_id"], "current_processing.ocr_job_id": source_ocr_job_id},
        {
            "$set": {
                "pipeline_summary.index_status": "NOT_STARTED",
                "current_processing.pending_index_job_id": None,
                "latest_error": None,
                "updated_at": utc_now(),
            }
        },
    )
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
        "source_processing_revision_id": (document.get("current_processing") or {}).get(
            "processing_revision_id"
        ),
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
    chunk_set = db.chunk_sets.find_one({"_id": set_oid}) or {}
    source_processing_revision_id = chunk_set.get("source_processing_revision_id")
    records = []
    for index, chunk in enumerate(chunks, start=1):
        metadata = chunk["metadata"]
        content_hash = stable_hash(chunk["content"])
        chunk_id = ObjectId(
            hashlib.sha256(f"{set_oid}:{index}:{content_hash}".encode("utf-8")).hexdigest()[:24]
        )
        records.append(
            {
                "_id": chunk_id,
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
                "parent_section_id": metadata.get("parent_section_id"),
                "source_processing_revision_id": source_processing_revision_id,
                "source_span": metadata.get("source_span") or {},
                "chapter_key": metadata.get("chapter_key") or "",
                "content_type": metadata.get("content_type", "text"),
                "semantic_type": metadata.get("semantic_type", "theory"),
                "information_density": metadata.get("information_density", 0),
                "token_count": metadata.get("token_count", 0),
                "token_budget": metadata.get("token_budget"),
                "token_budget_status": metadata.get("token_budget_status", "UNKNOWN"),
                "created_at": now,
            }
        )
    vector = db.vector_collections.find_one_and_update(
        {"provider": "CHROMA", "collection_name": collection_name},
        {
            "$set": {
                "updated_at": now,
            },
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
                "embedding_model_digest": embedding_model_manifest(collection_name)[
                    "model_digest"
                ],
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
    model_digest = embedding_model_manifest(collection_name)["model_digest"]
    if vector.get("embedding_model_digest") != model_digest:
        db.vector_collections.update_one(
            {"_id": vector["_id"]},
            {"$set": {"embedding_model_digest": model_digest, "updated_at": now}},
        )
        vector["embedding_model_digest"] = model_digest
    # A lease retry rebuilds the same candidate deterministically. Removing only
    # this inactive candidate never touches a previously active chunk set.
    db.chunk_embeddings.delete_many({"chunk_set_id": set_oid})
    db.document_chunks.delete_many({"chunk_set_id": set_oid})
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
    worker_id: str | None = None,
    fencing_token: int | None = None,
) -> None:
    db = get_database()
    document_oid = object_id(document_id)
    job_oid = object_id(chunk_job_id)
    set_oid = object_id(chunk_set_id)
    vector_oid = object_id(vector_collection_id) if vector_collection_id else None
    now = utc_now()
    with mongo_transaction() as session:
        job_filter: dict = {"_id": job_oid}
        if worker_id is not None:
            job_filter["worker_id"] = worker_id
        if fencing_token is not None:
            job_filter["fencing_token"] = fencing_token
        job = db.document_jobs.find_one(job_filter, {"status": 1}, session=session)
        if not job:
            raise RuntimeError("DOCUMENT_JOB_LEASE_LOST")
        if job and job.get("status") == "CANCELLED":
            db.chunk_sets.update_one(
                {"_id": set_oid},
                {
                    "$set": {
                        "status": "CANCELLED",
                        "completed_at": now,
                    }
                },
                session=session,
            )
            return
        target_set = db.chunk_sets.find_one({"_id": set_oid}, session=session)
        if not target_set:
            raise RuntimeError("CHUNK_SET_NOT_FOUND")
        document_filter: dict = {"_id": document_oid, "archived_at": None}
        if not dry_run:
            document_filter["current_processing.ocr_job_id"] = target_set.get(
                "source_ocr_job_id"
            )
        current_document = db.documents.find_one(document_filter, session=session)
        if not current_document:
            raise RuntimeError("DOCUMENT_ARCHIVED_OR_SOURCE_CHANGED")
        index_manifest_id = None
        if not dry_run:
            db.chunk_sets.update_many(
                {
                    "document_id": document_oid,
                    "_id": {"$ne": set_oid},
                    "status": "ACTIVE",
                },
                {"$set": {"status": "SUPERSEDED", "superseded_at": now}},
                session=session,
            )
        db.chunk_sets.update_one(
            {"_id": set_oid},
            {
                "$set": {
                    "status": "DRY_RUN" if dry_run else "ACTIVE",
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
        if not dry_run and vector_oid:
            vector = db.vector_collections.find_one({"_id": vector_oid}, session=session)
            chunk_hashes = [
                item.get("content_hash")
                for item in db.document_chunks.find(
                    {"chunk_set_id": set_oid},
                    {"content_hash": 1},
                    session=session,
                ).sort("chunk_no", 1)
            ]
            index_manifest_id = ObjectId()
            previous_manifest_id = (current_document.get("current_processing") or {}).get(
                "index_manifest_id"
            )
            db.index_manifests.update_many(
                {"document_id": document_oid, "status": "ACTIVE"},
                {"$set": {"status": "SUPERSEDED", "superseded_at": now}},
                session=session,
            )
            db.index_manifests.insert_one(
                {
                    "_id": index_manifest_id,
                    "schema_version": SCHEMA_VERSION,
                    "document_id": document_oid,
                    "chunk_set_id": set_oid,
                    "vector_collection_id": vector_oid,
                    "source_processing_revision_id": target_set.get(
                        "source_processing_revision_id"
                    ),
                    "source_job_id": job_oid,
                    "activation_kind": "CHUNK_INDEX",
                    "previous_manifest_id": previous_manifest_id,
                    "embedding_model": (vector or {}).get("embedding_model") or {},
                    "embedding_model_digest": (vector or {}).get("embedding_model_digest"),
                    "chunk_count": len(chunk_hashes),
                    "chunk_set_hash": stable_hash(chunk_hashes),
                    "status": "ACTIVE",
                    "created_at": now,
                },
                session=session,
            )
            db.chunk_sets.update_one(
                {"_id": set_oid},
                {"$set": {"index_manifest_id": index_manifest_id}},
                session=session,
            )
        job_result = db.document_jobs.update_one(
            job_filter,
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
        if not job_result.matched_count:
            raise RuntimeError("DOCUMENT_JOB_LEASE_LOST")
        document_fields = {"updated_at": now}
        if not dry_run:
            document_fields.update(
                {
                    "pipeline_summary.chunk_status": "COMPLETED",
                    "pipeline_summary.total_chunks": total_chunks,
                    "current_processing.chunk_set_id": set_oid,
                    "current_processing.vector_collection_id": vector_oid,
                    "current_processing.index_manifest_id": index_manifest_id,
                    "current_processing.pending_chunk_job_id": None,
                    "pipeline_summary.index_status": "COMPLETED",
                    "status": "READY",
                }
            )
        document_result = db.documents.update_one(
            document_filter,
            {"$set": document_fields},
            session=session,
        )
        if not document_result.matched_count:
            raise RuntimeError("DOCUMENT_ARCHIVED")


def activate_reindex_manifest(
    document_id: str,
    index_job_id: str,
    chunk_set_id: str,
    vector_collection_id: str,
    *,
    expected_vector_collection_id,
    chunk_count: int,
    worker_id: str | None = None,
    fencing_token: int | None = None,
) -> str:
    db = get_database()
    document_oid = object_id(document_id, "document_id")
    job_oid = object_id(index_job_id, "index_job_id")
    set_oid = object_id(chunk_set_id, "chunk_set_id")
    vector_oid = object_id(vector_collection_id, "vector_collection_id")
    expected_vector_oid = (
        object_id(expected_vector_collection_id, "expected_vector_collection_id")
        if expected_vector_collection_id
        else None
    )
    manifest_id = ObjectId(hashlib.sha256(str(job_oid).encode("utf-8")).hexdigest()[:24])
    now = utc_now()
    with mongo_transaction() as session:
        job_filter: dict = {"_id": job_oid, "status": "PROCESSING"}
        if worker_id is not None:
            job_filter["worker_id"] = worker_id
        if fencing_token is not None:
            job_filter["fencing_token"] = fencing_token
        if not db.document_jobs.find_one(job_filter, {"_id": 1}, session=session):
            raise RuntimeError("DOCUMENT_JOB_LEASE_LOST")
        existing = db.index_manifests.find_one({"_id": manifest_id}, session=session)
        if existing:
            active_document = db.documents.find_one(
                {
                    "_id": document_oid,
                    "current_processing.index_manifest_id": manifest_id,
                },
                {"_id": 1},
                session=session,
            )
            if existing.get("status") == "ACTIVE" and active_document:
                return str(manifest_id)
            raise RuntimeError("INDEX_MANIFEST_REPLAY_CONFLICT")
        document_filter = {
            "_id": document_oid,
            "archived_at": None,
            "current_processing.chunk_set_id": set_oid,
            "current_processing.vector_collection_id": expected_vector_oid,
        }
        document = db.documents.find_one(document_filter, session=session)
        if not document:
            raise RuntimeError("INDEX_ACTIVATION_CONFLICT")
        vector = db.vector_collections.find_one({"_id": vector_oid}, session=session)
        if not vector:
            raise RuntimeError("INDEX_VECTOR_COLLECTION_NOT_FOUND")
        hashes = [
            item.get("content_hash")
            for item in db.document_chunks.find(
                {"chunk_set_id": set_oid},
                {"content_hash": 1},
                session=session,
            ).sort("chunk_no", 1)
        ]
        if len(hashes) != chunk_count:
            raise RuntimeError("INDEX_MANIFEST_COUNT_MISMATCH")
        indexed_count = db.chunk_embeddings.count_documents(
            {
                "chunk_set_id": set_oid,
                "vector_collection_id": vector_oid,
                "status": "INDEXED",
                "$expr": {"$eq": ["$embedding_content_hash", "$chunk_content_hash"]},
            },
            session=session,
        )
        if indexed_count != chunk_count:
            raise RuntimeError("INDEX_MANIFEST_COVERAGE_MISMATCH")
        previous_manifest_id = (document.get("current_processing") or {}).get(
            "index_manifest_id"
        )
        db.index_manifests.update_many(
            {"document_id": document_oid, "status": "ACTIVE"},
            {"$set": {"status": "SUPERSEDED", "superseded_at": now}},
            session=session,
        )
        db.index_manifests.insert_one(
            {
                "_id": manifest_id,
                "schema_version": SCHEMA_VERSION,
                "document_id": document_oid,
                "chunk_set_id": set_oid,
                "vector_collection_id": vector_oid,
                "source_processing_revision_id": document.get("current_processing", {}).get(
                    "processing_revision_id"
                ),
                "source_job_id": job_oid,
                "activation_kind": "REINDEX",
                "previous_manifest_id": previous_manifest_id,
                "embedding_model": (vector or {}).get("embedding_model") or {},
                "embedding_model_digest": (vector or {}).get("embedding_model_digest"),
                "chunk_count": chunk_count,
                "chunk_set_hash": stable_hash(hashes),
                "status": "ACTIVE",
                "created_at": now,
            },
            session=session,
        )
        result = db.documents.update_one(
            document_filter,
            {
                "$set": {
                    "current_processing.vector_collection_id": vector_oid,
                    "current_processing.index_manifest_id": manifest_id,
                    "current_processing.pending_index_job_id": None,
                    "pipeline_summary.index_status": "COMPLETED",
                    "status": "READY",
                    "updated_at": now,
                }
            },
            session=session,
        )
        if not result.matched_count:
            raise RuntimeError("INDEX_ACTIVATION_CONFLICT")
    return str(manifest_id)


def rollback_index_manifest(document_id: str, expected_manifest_id: str) -> dict:
    db = get_database()
    document_oid = object_id(document_id, "document_id")
    expected_oid = object_id(expected_manifest_id, "index_manifest_id")
    now = utc_now()
    with mongo_transaction() as session:
        current = db.index_manifests.find_one(
            {"_id": expected_oid, "document_id": document_oid, "status": "ACTIVE"},
            session=session,
        )
        if not current or not current.get("previous_manifest_id"):
            raise ValueError("INDEX_ROLLBACK_NOT_AVAILABLE")
        previous = db.index_manifests.find_one(
            {"_id": current["previous_manifest_id"], "document_id": document_oid},
            session=session,
        )
        if not previous or previous.get("chunk_set_id") != current.get("chunk_set_id"):
            raise ValueError("INDEX_ROLLBACK_SOURCE_MISMATCH")
        expected_count = db.document_chunks.count_documents(
            {"chunk_set_id": previous["chunk_set_id"]}, session=session
        )
        indexed_count = db.chunk_embeddings.count_documents(
            {
                "chunk_set_id": previous["chunk_set_id"],
                "vector_collection_id": previous["vector_collection_id"],
                "status": "INDEXED",
                "$expr": {"$eq": ["$embedding_content_hash", "$chunk_content_hash"]},
            },
            session=session,
        )
        if expected_count == 0 or indexed_count != expected_count:
            raise ValueError("INDEX_ROLLBACK_COVERAGE_MISMATCH")
        db.index_manifests.update_one(
            {"_id": current["_id"], "status": "ACTIVE"},
            {"$set": {"status": "ROLLED_BACK", "rolled_back_at": now}},
            session=session,
        )
        db.index_manifests.update_one(
            {"_id": previous["_id"]},
            {"$set": {"status": "ACTIVE", "reactivated_at": now}},
            session=session,
        )
        result = db.documents.update_one(
            {
                "_id": document_oid,
                "current_processing.index_manifest_id": current["_id"],
            },
            {
                "$set": {
                    "current_processing.vector_collection_id": previous[
                        "vector_collection_id"
                    ],
                    "current_processing.index_manifest_id": previous["_id"],
                    "pipeline_summary.index_status": "COMPLETED",
                    "updated_at": now,
                }
            },
            session=session,
        )
        if not result.matched_count:
            raise RuntimeError("INDEX_ROLLBACK_CONFLICT")
    return {
        "document_id": str(document_oid),
        "active_manifest_id": str(previous["_id"]),
        "vector_collection_id": str(previous["vector_collection_id"]),
        "rolled_back_manifest_id": str(current["_id"]),
    }


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
