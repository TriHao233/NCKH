"""Retryable PostgreSQL outbox delivery to MongoDB vector collections."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from bson import ObjectId

from core.database import get_database, mongo_transaction
from core.postgres import postgres_connection

logger = logging.getLogger(__name__)


def _claim(worker_id: str) -> dict | None:
    with postgres_connection() as conn:
        return conn.execute(
            """WITH available AS (
                   SELECT id FROM outbox_events
                   WHERE ((status='PENDING' AND next_attempt_at <= now())
                       OR (status='PROCESSING' AND lease_expires_at <= now()))
                   ORDER BY created_at, id LIMIT 1 FOR UPDATE SKIP LOCKED
               )
               UPDATE outbox_events AS event
               SET status='PROCESSING', attempts=attempts+1,
                   lease_owner=%s, lease_expires_at=now()+interval '120 seconds',
                   updated_at=now()
               FROM available WHERE event.id=available.id
               RETURNING event.*""",
            (worker_id,),
        ).fetchone()


def _deliver(event: dict) -> None:
    if event["event_type"] == "document.chunk_delete":
        _delete_chunk_set(event["payload"])
        return
    if event["event_type"] == "document.chunk_archive":
        _archive_chunk_set(event["payload"])
        return
    if event["event_type"] != "document.chunk_cancel":
        raise ValueError(f"Unsupported outbox event type: {event['event_type']}")
    payload = event["payload"]
    job_id = ObjectId(payload["job_id"])
    database = get_database()
    chunk_sets = list(database.chunk_sets.find({"chunk_job_id": job_id}, {"_id": 1}))
    chunk_set_ids = [item["_id"] for item in chunk_sets]
    now = datetime.now(timezone.utc)
    error = {"message": payload.get("error_message") or "Job đã bị hủy", "at": now}
    database.chunk_sets.update_many(
        {"chunk_job_id": job_id},
        {"$set": {"status": "CANCELLED", "error": error, "completed_at": now}},
    )
    if chunk_set_ids:
        database.chunk_embeddings.update_many(
            {"chunk_set_id": {"$in": chunk_set_ids}, "status": "PENDING"},
            {"$set": {"status": "CANCELLED", "error": error, "updated_at": now}},
        )


def _archive_chunk_set(payload: dict) -> None:
    document_id = payload["document_id"]
    chunk_set_id = payload["chunk_set_id"]
    with postgres_connection() as conn:
        document = conn.execute(
            "SELECT active_chunk_set_id, payload FROM documents WHERE id=%s",
            (document_id,),
        ).fetchone()
    if not document:
        raise LookupError("Document missing before vector archive")
    pending = (document["payload"] or {}).get("pending_processing") or {}
    if (document["active_chunk_set_id"] == chunk_set_id
            or pending.get("chunk_set_id") == chunk_set_id):
        raise RuntimeError("Lineage became active or pending before archive delivery")
    collection = get_database().chunk_sets
    existing = collection.find_one({"_id": ObjectId(chunk_set_id),
                                    "document_id": ObjectId(document_id)})
    if not existing:
        raise LookupError("Chunk set missing before vector archive")
    if existing.get("archived_at"):
        if existing.get("archive_operation_id") == payload["operation_id"]:
            return
        raise RuntimeError("Chunk set already archived by a different operation")
    now = datetime.now(timezone.utc)
    result = collection.update_one(
        {"_id": ObjectId(chunk_set_id), "document_id": ObjectId(document_id),
         "archived_at": None},
        {"$set": {"archived_at": now, "archived_by": payload["actor"],
                  "archive_reason": payload["reason"],
                  "archive_operation_id": payload["operation_id"]}},
    )
    if not result.modified_count:
        raise RuntimeError("Chunk set archive raced with another update")


def _delete_chunk_set(payload: dict) -> None:
    document_id = payload["document_id"]
    chunk_set_id = payload["chunk_set_id"]
    with postgres_connection() as conn:
        row = conn.execute(
            """SELECT status FROM document_lineage_events
               WHERE operation_id=%s AND event_type='PERMANENT_DELETE_REQUESTED'""",
            (payload["operation_id"],),
        ).fetchone()
        if not row or row["status"] not in {"DELETE_QUEUED", "DELETED"}:
            raise RuntimeError("Delete request is not queued")
        if row["status"] == "DELETED":
            return
        document = conn.execute(
            "SELECT active_chunk_set_id, payload FROM documents WHERE id=%s",
            (document_id,),
        ).fetchone()
        if not document:
            raise LookupError("Document missing before vector deletion")
        pending = (document["payload"] or {}).get("pending_processing") or {}
        if (document["active_chunk_set_id"] == chunk_set_id
                or pending.get("chunk_set_id") == chunk_set_id):
            raise RuntimeError("Lineage became active or pending before deletion")
        rollback_ref = conn.execute(
            """SELECT 1 FROM document_lineage_events
               WHERE document_id=%s AND rollback_available
                 AND (from_snapshot->>'chunk_set_id'=%s
                      OR to_snapshot->>'chunk_set_id'=%s) LIMIT 1""",
            (document_id, chunk_set_id, chunk_set_id),
        ).fetchone()
        if rollback_ref:
            raise RuntimeError("Lineage became rollbackable before deletion")
    database = get_database()
    set_oid = ObjectId(chunk_set_id)
    document_oid = ObjectId(document_id)
    chunk_set = database.chunk_sets.find_one({"_id": set_oid, "document_id": document_oid})
    if chunk_set and not chunk_set.get("archived_at"):
        raise ValueError("Chunk set must be archived before deletion")
    embeddings = list(database.chunk_embeddings.find({"chunk_set_id": set_oid}))
    external_ids = [item["external_vector_id"] for item in embeddings
                    if item.get("external_vector_id")]
    if external_ids:
        vector = database.vector_collections.find_one(
            {"_id": ObjectId(payload["vector_collection_id"])}
        )
        if not vector:
            raise LookupError("Vector collection missing before Chroma deletion")
        from modules.rag.chromadb_engine import get_collection
        get_collection(vector["collection_name"]).delete(ids=external_ids)
    with mongo_transaction() as session:
        database.chunk_embeddings.delete_many({"chunk_set_id": set_oid}, session=session)
        database.document_chunks.delete_many({"chunk_set_id": set_oid}, session=session)
        database.chunk_sets.delete_one({"_id": set_oid, "document_id": document_oid},
                                       session=session)
    other_set = database.chunk_sets.find_one({
        "document_id": document_oid,
        "source_ocr_job_id": ObjectId(payload["ocr_job_id"]),
    })
    with postgres_connection() as conn:
        if not other_set:
            conn.execute(
                "DELETE FROM document_pages WHERE document_id=%s AND ocr_job_id=%s",
                (document_id, payload["ocr_job_id"]),
            )
            conn.execute(
                "DELETE FROM document_jobs WHERE id=%s AND document_id=%s",
                (payload["ocr_job_id"], document_id),
            )
        conn.execute(
            """UPDATE document_lineage_events
               SET status='DELETED',
                   payload=jsonb_set(payload, '{status}', '"DELETED"'::jsonb)
               WHERE operation_id=%s AND status='DELETE_QUEUED'""",
            (payload["operation_id"],),
        )


def process_available_outbox_once(worker_id: str | None = None) -> bool:
    """Deliver at most one event; retries use the same event key and lease."""
    worker_id = worker_id or uuid4().hex
    event = _claim(worker_id)
    if not event:
        return False
    try:
        _deliver(event)
    except Exception as exc:
        delay = min(300, 2 ** min(event["attempts"], 8))
        with postgres_connection() as conn:
            conn.execute(
                """UPDATE outbox_events
                   SET status='PENDING', lease_owner=NULL, lease_expires_at=NULL,
                       next_attempt_at=now()+(%s * interval '1 second'),
                       last_error=%s, updated_at=now()
                   WHERE id=%s AND lease_owner=%s AND status='PROCESSING'""",
                (delay, type(exc).__name__, event["id"], worker_id),
            )
        logger.warning("Outbox delivery failed for %s [%s]", event["event_type"], event["id"])
    else:
        with postgres_connection() as conn:
            if event["event_type"] == "document.chunk_archive":
                conn.execute(
                    """UPDATE document_lineage_events
                       SET status='COMPLETED',
                           payload=jsonb_set(payload, '{status}', '"COMPLETED"'::jsonb)
                       WHERE operation_id=%s AND event_type='ARCHIVE'""",
                    (event["payload"]["operation_id"],),
                )
            conn.execute(
                """UPDATE outbox_events
                   SET status='DONE', lease_owner=NULL, lease_expires_at=NULL,
                       last_error=NULL, updated_at=now()
                   WHERE id=%s AND lease_owner=%s AND status='PROCESSING'""",
                (event["id"], worker_id),
            )
    return True
