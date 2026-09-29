"""Run with RUN_POSTGRES_INTEGRATION=1 and POSTGRES_DSN on a test database."""

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from bson import ObjectId

from core.config import settings
from core.postgres import postgres_connection
from modules.questions.postgres_evaluation_jobs import PostgresEvaluationJobs
from modules.questions.postgres_repository import PostgresQuestionRepository
from modules.users.postgres_repository import PostgresUserRepository


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="Requires an explicitly configured PostgreSQL test database",
)


def test_evaluation_queue_dedupes_claims_and_finishes_with_version_guard(monkeypatch):
    monkeypatch.setattr(settings, "user_store", "postgres")
    monkeypatch.setattr(settings, "catalog_store", "postgres")
    suffix = uuid4().hex[:12]
    user = PostgresUserRepository().create({
        "firebase_uid": f"eval-{suffix}", "email": f"eval-{suffix}@example.test",
        "display_name": "Teacher", "role": "Teacher",
    })
    now = datetime.now(timezone.utc)
    question_id, version_id, job_id = ObjectId(), ObjectId(), ObjectId()
    questions = PostgresQuestionRepository()
    jobs = PostgresEvaluationJobs()
    try:
        questions.create({
            "_id": question_id, "schema_version": 2,
            "question_code": f"Q-{suffix}",
            "created_by_user_id": user["_id"],
            "current_version": 1, "current_version_id": version_id,
            "approved_version_id": None, "lifecycle_status": "ACTIVE",
            "review_status": "DRAFT", "evaluation_status": "NOT_STARTED",
            "publication_status": "NOT_PUBLISHED",
            "review_assignment": {"status": "UNASSIGNED"},
            "created_at": now, "updated_at": now,
        }, {
            "_id": version_id, "question_id": question_id, "version": 1,
            "origin": "MANUAL", "content": "Câu hỏi đánh giá",
            "question_data": {"options": {"A": "đúng"}, "correct_answer": "A"},
            "classification": {}, "clos": [], "sources": [],
            "content_hash": f"hash-{suffix}",
            "created_by_user_id": user["_id"], "created_at": now,
        })
        request = {
            "_id": job_id, "question_id": question_id,
            "question_version_id": version_id,
            "requested_by_user_id": user["_id"],
            "status": "QUEUED", "evaluator_model_code": "gemini",
            "dedupe_key": f"eval-{suffix}",
            "model_snapshot": {"model_name": "gemini"},
            "policy_snapshot": {"version": 1},
            "prompt_snapshot": {"key": "quality"},
            "source_snapshot": [], "queued_at": now,
            "created_at": now, "updated_at": now,
        }
        queued = jobs.enqueue(question_id, version_id, request)
        assert queued["attempt_no"] == 1
        assert jobs.enqueue(question_id, version_id, {**request, "_id": ObjectId()})["_id"] == job_id
        assert jobs.next_queued_id() == str(job_id)
        claimed = jobs.claim(job_id, "worker-a")
        assert claimed["status"] == "PROCESSING"
        assert claimed["processing_attempt_count"] == 1
        assert jobs.claim(job_id, "worker-b") is None
        assert jobs.heartbeat(job_id, "worker-b") is False
        assert jobs.heartbeat(job_id, "worker-a") is True
        evaluated, _ = questions.record_evaluation({
            "_id": ObjectId(), "question_id": question_id,
            "question_version_id": version_id, "evaluation_job_id": job_id,
            "requested_by_user_id": user["_id"],
            "evaluator_model": {"model_code": "gemini"},
            "policy": {"version": 1}, "scores": {"overall": 0.8},
            "color": "GREEN", "passed": True, "created_at": now,
        }, expected_version_id=version_id,
            evaluation_status="PASSED",
            quality_summary={"overall_score": 0.8, "color": "GREEN"},
            require_active_job=True)
        assert evaluated["evaluation_status"] == "PASSED"
        assert jobs.finish(job_id, "worker-b", {"passed": True}) is False
        assert jobs.finish(job_id, "worker-a", {"passed": True}) is True
        assert jobs.get(job_id)["status"] == "COMPLETED"
        assert jobs.next_queued_id() is None

        with postgres_connection() as conn:
            conn.execute(
                """UPDATE questions SET evaluation_status='FAILED',
                   payload=jsonb_set(payload, '{evaluation_status}', '"FAILED"'::jsonb)
                   WHERE id=%s""",
                (str(question_id),),
            )
        retry_id = ObjectId()
        retried = jobs.enqueue(question_id, version_id, {
            **request, "_id": retry_id, "dedupe_key": f"retry-{suffix}",
            "max_attempts": 2,
        })
        assert retried["attempt_no"] == 2
        assert jobs.claim(retry_id, "worker-b")["processing_attempt_count"] == 1
        scheduled = jobs.retry_or_dead_letter(retry_id, "worker-b", "temporary",
                                              duration_ms=10)
        assert scheduled["status"] == "QUEUED"
        assert jobs.claim(retry_id, "worker-b") is None
        with postgres_connection() as conn:
            conn.execute(
                "UPDATE evaluation_jobs SET next_attempt_at=now()-interval '1 second' "
                "WHERE id=%s", (str(retry_id),),
            )
        assert jobs.claim(retry_id, "worker-b")["processing_attempt_count"] == 2
        dead = jobs.retry_or_dead_letter(retry_id, "worker-b", "permanent",
                                         duration_ms=20)
        assert dead["status"] == "ERROR"
        assert dead["dead_lettered_at"] is not None
        assert questions.find_pair(question_id)[0]["evaluation_status"] == "ERROR"
        changed = jobs.mark_enqueue_error(
            question_id, expected_version=1, evaluator_model_code="gemini",
            message="provider unavailable",
        )
        assert changed["quality_summary"]["error"]["stage"] == "ENQUEUE"
    finally:
        with postgres_connection() as conn:
            conn.execute("DELETE FROM audit_logs WHERE entity_id=%s", (str(question_id),))
            conn.execute("DELETE FROM question_evaluations WHERE question_id=%s",
                         (str(question_id),))
            conn.execute("DELETE FROM evaluation_jobs WHERE question_id=%s",
                         (str(question_id),))
            conn.execute("UPDATE questions SET current_version_id=NULL WHERE id=%s",
                         (str(question_id),))
            conn.execute("DELETE FROM question_versions WHERE question_id=%s",
                         (str(question_id),))
            conn.execute("DELETE FROM questions WHERE id=%s", (str(question_id),))
            conn.execute("DELETE FROM users WHERE id=%s", (str(user["_id"]),))
