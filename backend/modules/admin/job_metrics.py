from datetime import datetime, timezone


def _seconds_since(value: datetime | None, now: datetime) -> int | None:
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return max(0, int((now - value).total_seconds()))


def collect_job_metrics(database) -> dict:
    now = datetime.now(timezone.utc)
    generation = database.generation_jobs
    evaluation = database.evaluation_jobs
    documents = database.document_jobs
    oldest_generation = generation.find_one(
        {"status": "queued"}, sort=[("created_at", 1)], projection={"created_at": 1}
    )
    oldest_evaluation = evaluation.find_one(
        {"status": "QUEUED"}, sort=[("queued_at", 1)], projection={"queued_at": 1}
    )
    oldest_document = documents.find_one(
        {"status": "QUEUED"}, sort=[("queued_at", 1)], projection={"queued_at": 1}
    )
    return {
        "observed_at": now,
        "queues": {
            "generation": {
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
            "evaluation": {
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
            "document": {
                "queued": documents.count_documents({"status": "QUEUED"}),
                "processing": documents.count_documents({"status": "PROCESSING"}),
                "oldest_queued_seconds": _seconds_since(
                    (oldest_document or {}).get("queued_at"), now
                ),
            },
        },
        "llm_slots": {
            "in_use": database.llm_slots.count_documents(
                {"holder_id": {"$ne": None}, "lease_expires_at": {"$gt": now}}
            ),
            "expired": database.llm_slots.count_documents(
                {"holder_id": {"$ne": None}, "lease_expires_at": {"$lte": now}}
            ),
        },
    }
