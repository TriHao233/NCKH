from datetime import datetime, timezone

from core.config import settings
from core.postgres import postgres_connection
from modules.generation.llm import postgres_slots


def _seconds_since(value: datetime | None, now: datetime) -> int | None:
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return max(0, int((now - value).total_seconds()))


def _postgres_document_queue_metrics(now: datetime) -> dict:
    with postgres_connection() as conn:
        row = conn.execute(
            """SELECT
                   count(*) FILTER (WHERE status='QUEUED') AS queued,
                   count(*) FILTER (WHERE status='PROCESSING') AS processing,
                   min(created_at) FILTER (WHERE status='QUEUED') AS oldest_queued
               FROM document_jobs"""
        ).fetchone()
    return {
        "queued": row["queued"], "processing": row["processing"],
        "oldest_queued_seconds": _seconds_since(row["oldest_queued"], now),
    }


def _postgres_evaluation_queue_metrics(now: datetime) -> dict:
    from modules.questions.postgres_evaluation_jobs import PostgresEvaluationJobs
    row = PostgresEvaluationJobs().queue_metrics()
    return {
        "queued": row["queued"], "processing": row["processing"],
        "retry_wait": row["retry_wait"], "dead_lettered": row["dead_lettered"],
        "expired_leases": row["expired_leases"],
        "oldest_queued_seconds": _seconds_since(row["oldest_queued"], now),
    }


def _postgres_generation_queue_metrics(now: datetime) -> dict:
    from modules.generation.postgres_store import PostgresGenerationStore
    row = PostgresGenerationStore().queue_metrics()
    return {
        "queued": row["queued"], "processing": row["processing"],
        "retry_wait": row["retry_wait"], "dead_lettered": row["dead_lettered"],
        "expired_leases": row["expired_leases"],
        "oldest_queued_seconds": _seconds_since(row["oldest_queued"], now),
    }


def collect_job_metrics(database) -> dict:
    now = datetime.now(timezone.utc)
    generation = database.generation_jobs if settings.generation_store != "postgres" else None
    evaluation = database.evaluation_jobs if settings.question_store != "postgres" else None
    documents = database.document_jobs if settings.document_store != "postgres" else None
    oldest_generation = generation.find_one(
        {"status": "queued"}, sort=[("created_at", 1)], projection={"created_at": 1}
    ) if generation is not None else None
    oldest_evaluation = evaluation.find_one(
        {"status": "QUEUED"}, sort=[("queued_at", 1)], projection={"queued_at": 1}
    ) if evaluation is not None else None
    oldest_document = (documents.find_one(
        {"status": "QUEUED"}, sort=[("queued_at", 1)], projection={"queued_at": 1}
    ) if documents is not None else None)
    return {
        "observed_at": now,
        "queues": {
            "generation": _postgres_generation_queue_metrics(now) if generation is None else {
                "queued": generation.count_documents({"status": "queued"}),
                "processing": generation.count_documents({"status": "processing"}),
                "retry_wait": generation.count_documents(
                    {"status": "queued", "next_attempt_at": {"$gt": now}}
                ),
                "dead_lettered": generation.count_documents({"dead_lettered_at": {"$exists": True}}),
                "expired_leases": generation.count_documents(
                    {"status": "processing", "lease_expires_at": {"$lte": now}}
                ),
                "oldest_queued_seconds": _seconds_since(
                    (oldest_generation or {}).get("created_at"), now
                ),
            },
            "evaluation": _postgres_evaluation_queue_metrics(now) if evaluation is None else {
                "queued": evaluation.count_documents({"status": "QUEUED"}),
                "processing": evaluation.count_documents({"status": "PROCESSING"}),
                "retry_wait": evaluation.count_documents(
                    {"status": "QUEUED", "next_attempt_at": {"$gt": now}}
                ),
                "dead_lettered": evaluation.count_documents({"dead_lettered_at": {"$exists": True}}),
                "expired_leases": evaluation.count_documents(
                    {"status": "PROCESSING", "lease_expires_at": {"$lte": now}}
                ),
                "oldest_queued_seconds": _seconds_since(
                    (oldest_evaluation or {}).get("queued_at"), now
                ),
            },
            "document": _postgres_document_queue_metrics(now) if documents is None else {
                "queued": documents.count_documents({"status": "QUEUED"}),
                "processing": documents.count_documents({"status": "PROCESSING"}),
                "oldest_queued_seconds": _seconds_since(
                    (oldest_document or {}).get("queued_at"), now
                ),
            },
        },
        "llm_slots": (
            postgres_slots.counts() if settings.llm_slot_store == "postgres" else {
                "in_use": database.llm_slots.count_documents(
                    {"holder_id": {"$ne": None}, "lease_expires_at": {"$gt": now}}
                ),
                "expired": database.llm_slots.count_documents(
                    {"holder_id": {"$ne": None}, "lease_expires_at": {"$lte": now}}
                ),
            }
        ),
    }
