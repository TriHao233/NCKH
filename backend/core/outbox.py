"""Retryable PostgreSQL outbox delivery to MongoDB vector collections."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from bson import ObjectId

from core.database import get_database
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
            conn.execute(
                """UPDATE outbox_events
                   SET status='DONE', lease_owner=NULL, lease_expires_at=NULL,
                       last_error=NULL, updated_at=now()
                   WHERE id=%s AND lease_owner=%s AND status='PROCESSING'""",
                (event["id"], worker_id),
            )
    return True
