from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from core.config import settings
from core.database import get_database

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stale_time_filter(cutoff: datetime) -> dict:
    return {
        "$or": [
            {"updated_at": {"$lt": cutoff}},
            {"updated_at": {"$exists": False}, "started_at": {"$lt": cutoff}},
            {
                "updated_at": {"$exists": False},
                "started_at": None,
                "queued_at": {"$lt": cutoff},
            },
        ]
    }


def recover_stale_jobs(timeout_minutes: int | None = None) -> dict:
    db = get_database()
    now = utc_now()
    timeout = timeout_minutes or settings.job_recovery_timeout_minutes
    cutoff = now - timedelta(minutes=max(timeout, 1))
    message = (
        "Job was active before backend startup and exceeded "
        f"{timeout} minute recovery timeout"
    )
    results = {
        "generation_failed": _recover_generation_jobs(db, cutoff, now, message),
        "evaluation_stale": _recover_evaluation_jobs(db, cutoff, now, message),
        "document_failed": _recover_document_jobs(db, cutoff, now, message),
    }
    total = sum(results.values())
    if total:
        logger.warning("Recovered stale background jobs on startup: %s", results)
    return results


def _recover_generation_jobs(db, cutoff: datetime, now: datetime, message: str) -> int:
    result = db.generation_jobs.update_many(
        {
            "status": "processing",
            **_stale_time_filter(cutoff),
        },
        {
            "$set": {
                "status": "failed",
                "error_message": message,
                "updated_at": now,
            }
        },
    )
    return result.modified_count


def _recover_evaluation_jobs(db, cutoff: datetime, now: datetime, message: str) -> int:
    active_jobs = list(
        db.evaluation_jobs.find(
            {
                "status": {"$in": ["QUEUED", "PROCESSING"]},
                **_stale_time_filter(cutoff),
            }
        )
    )
    error = {"message": message, "at": now}
    for job in active_jobs:
        db.evaluation_jobs.update_one(
            {"_id": job["_id"], "status": {"$in": ["QUEUED", "PROCESSING"]}},
            {
                "$set": {
                    "status": "STALE",
                    "error": error,
                    "finished_at": now,
                    "updated_at": now,
                }
            },
        )
        db.questions.update_one(
            {
                "_id": job.get("question_id"),
                "evaluation_status": {"$in": ["QUEUED", "PROCESSING"]},
                "quality_summary.latest_evaluation_job_id": job["_id"],
            },
            {
                "$set": {
                    "evaluation_status": "STALE",
                    "quality_summary.error": error,
                    "updated_at": now,
                }
            },
        )
    return len(active_jobs)


def _recover_document_jobs(db, cutoff: datetime, now: datetime, message: str) -> int:
    active_jobs = list(
        db.document_jobs.find(
            {
                "status": {"$in": ["QUEUED", "PROCESSING"]},
                **_stale_time_filter(cutoff),
            }
        )
    )
    error = {"message": message, "at": now}
    for job in active_jobs:
        run_attempt = int(job.get("run_attempt", 0))
        retryable = job.get("job_type") in {"OCR", "CHUNK", "INDEX"} and run_attempt < settings.job_max_attempts
        next_status = "QUEUED" if retryable else "FAILED"
        fields = {
            "status": next_status,
            "error": error,
            "worker_id": None,
            "lease_expires_at": None,
            "heartbeat_at": None,
            "updated_at": now,
        }
        if retryable:
            fields["queued_at"] = now
            fields["finished_at"] = None
        else:
            fields["finished_at"] = now
        db.document_jobs.update_one(
            {"_id": job["_id"], "status": {"$in": ["QUEUED", "PROCESSING"]}},
            {"$set": fields},
        )
        job_type = str(job.get("job_type") or "UNKNOWN").lower()
        db.documents.update_one(
            {"_id": job.get("document_id"), "archived_at": None},
            {
                "$set": {
                    "status": "PROCESSING" if retryable else "FAILED",
                    f"pipeline_summary.{job_type}_status": next_status,
                    "latest_error": {
                        "job_id": job["_id"],
                        "job_type": job.get("job_type"),
                        "message": message,
                        "at": now,
                    },
                    "updated_at": now,
                }
            },
        )
        if job.get("job_type") == "OCR" and job.get("processing_revision_id"):
            db.document_processing_revisions.update_one(
                {"_id": job["processing_revision_id"]},
                {
                    "$set": {
                        "status": next_status,
                        "error": error,
                        "updated_at": now,
                        **({"completed_at": now} if not retryable else {}),
                    }
                },
            )
        if job.get("job_type") == "CHUNK" and not retryable:
            chunk_sets = list(
                db.chunk_sets.find(
                    {"chunk_job_id": job["_id"], "status": "PROCESSING"},
                    {"_id": 1},
                )
            )
            chunk_set_ids = [chunk_set["_id"] for chunk_set in chunk_sets]
            db.chunk_sets.update_many(
                {"chunk_job_id": job["_id"], "status": "PROCESSING"},
                {
                    "$set": {
                        "status": "FAILED",
                        "error": error,
                        "completed_at": now,
                    }
                },
            )
            if chunk_set_ids:
                db.chunk_embeddings.update_many(
                    {"status": "PENDING", "chunk_set_id": {"$in": chunk_set_ids}},
                    {"$set": {"status": "FAILED", "error": error, "updated_at": now}},
                )
    return len(active_jobs)
