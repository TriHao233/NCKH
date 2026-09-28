"""Run with RUN_POSTGRES_INTEGRATION=1 and POSTGRES_DSN on a test database."""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from bson import ObjectId

from core import job_recovery, job_worker
from core.config import settings
from core.postgres import postgres_connection
from modules.questions import workflow_service as workflow_module
from modules.questions.postgres_evaluation_jobs import PostgresEvaluationJobs
from modules.questions.postgres_repository import PostgresQuestionRepository
from modules.questions.workflow_schemas import EvaluationScores
from modules.questions.workflow_service import QuestionWorkflowService
from modules.users.postgres_repository import PostgresUserRepository


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="Requires an explicitly configured PostgreSQL test database",
)

MODEL = {"model_code": "fake-eval", "model_name": "Fake", "runtime": "TEST"}


class FakeLlm:
    def __init__(self, outcome):
        self.outcome = outcome
        self.runtime_snapshot = MODEL

    async def generate_text(self, _prompt):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _stub_pipeline(service, monkeypatch, outcome):
    scores = EvaluationScores(faithfulness=0.9, contextual_relevancy=0.9,
                              answer_relevancy=0.9, bloom_alignment=0.9,
                              clo_alignment=0.9)
    monkeypatch.setattr(service, "_build_evaluation_prompt",
                        lambda *_a, **_k: ("prompt", {"key": "quality"}, []))
    monkeypatch.setattr(service, "_retrieve_evaluation_sources",
                        lambda _v: ([], {"strategy": "test"}))
    monkeypatch.setattr(service, "_parse_llm_evaluation",
                        lambda _raw: (scores, {"summary": "ok"}, {}))
    monkeypatch.setattr(service, "_validate_model_evidence", lambda evidence, _s: evidence)
    monkeypatch.setattr(service, "_enforce_grounding_policy",
                        lambda sc, fb, _ev: (sc, fb))
    monkeypatch.setattr(service, "_apply_evaluation_guardrails",
                        lambda sc, fb, ev, _v: (sc, fb, ev))
    monkeypatch.setattr(service, "_validate_llm_evaluation_consistency",
                        lambda *_a: {"consistent": True})
    monkeypatch.setattr(workflow_module, "get_llm_service",
                        lambda *_a, **_k: FakeLlm(outcome))


def test_worker_runs_evaluation_jobs_through_postgres(monkeypatch):
    for key in ("user_store", "catalog_store", "question_store"):
        monkeypatch.setattr(settings, key, "postgres")
    monkeypatch.setattr(settings, "ai_config_store", "mongo")
    monkeypatch.setattr(settings, "evaluation_fallback_provider", "")
    monkeypatch.setattr(settings, "job_max_attempts", 3)
    suffix = uuid4().hex[:12]
    user = PostgresUserRepository().create({
        "firebase_uid": f"worker-{suffix}", "email": f"worker-{suffix}@example.test",
        "display_name": "Teacher", "role": "Teacher",
    })
    now = datetime.now(timezone.utc)
    question_id, version_id = ObjectId(), ObjectId()
    questions = PostgresQuestionRepository()
    jobs = PostgresEvaluationJobs()
    try:
        questions.create({
            "_id": question_id, "schema_version": 2, "question_code": f"W-{suffix}",
            "created_by_user_id": user["_id"],
            "current_version": 1, "current_version_id": version_id,
            "approved_version_id": None, "lifecycle_status": "ACTIVE",
            "review_status": "PENDING", "evaluation_status": "NOT_STARTED",
            "publication_status": "NOT_PUBLISHED",
            "review_assignment": {"status": "UNASSIGNED"},
            "created_at": now, "updated_at": now,
        }, {
            "_id": version_id, "question_id": question_id, "version": 1,
            "origin": "MANUAL", "content": "Câu hỏi worker",
            "question_data": {"options": {"A": "đúng"}, "correct_answer": "A"},
            "classification": {}, "clos": [], "sources": [],
            "content_hash": f"hash-{suffix}",
            "created_by_user_id": user["_id"], "created_at": now,
        })
        service = QuestionWorkflowService(None)
        assert service.evaluation_jobs is not None

        # Lỗi tạm thời: job quay lại hàng đợi với backoff, câu hỏi hiện QUEUED.
        _stub_pipeline(service, monkeypatch, RuntimeError("provider timeout"))
        queued = service.enqueue_auto_evaluation(
            str(question_id), expected_version=1, requested_by_user_id=user["_id"],
            evaluator_model_code="fake-eval", model_snapshot=MODEL,
        )
        job_id = queued["_id"]
        assert queued["attempt_no"] == 1
        assert service.enqueue_auto_evaluation(
            str(question_id), expected_version=1, requested_by_user_id=user["_id"],
            evaluator_model_code="fake-eval", model_snapshot=MODEL,
        )["_id"] == job_id
        assert job_worker.get_next_queued_evaluation_job_id() == job_id
        retried = asyncio.run(service.process_evaluation_job(job_id, "worker-a"))
        assert retried["status"] == "QUEUED"
        stored = jobs.get(job_id)
        assert stored["error"]["message"] == "provider timeout"
        assert stored["retrieval_snapshot"] == {"strategy": "test"}
        assert questions.find_pair(question_id)[0]["evaluation_status"] == "QUEUED"
        assert asyncio.run(service.process_evaluation_job(job_id, "worker-a")) is None

        # Hết backoff: lần chạy thành công ghi evaluation và hoàn tất job cùng version.
        with postgres_connection() as conn:
            conn.execute("UPDATE evaluation_jobs SET next_attempt_at=now()-interval '1 second' "
                         "WHERE id=%s", (job_id,))
        _stub_pipeline(service, monkeypatch, '{"ok": true}')
        evaluation = asyncio.run(service.process_evaluation_job(job_id, "worker-b"))
        assert evaluation["passed"] is True
        finished = jobs.get(job_id)
        assert finished["status"] == "COMPLETED"
        assert finished["result"]["passed"] is True
        assert finished["duration_ms"] is not None
        assert finished["expires_at"] is not None
        assert service.evaluation_job_state(job_id)["status"] == "COMPLETED"
        question = questions.find_pair(question_id)[0]
        assert question["evaluation_status"] == "PASSED"
        assert question["quality_summary"]["latest_evaluation_job_id"] == ObjectId(job_id)

        # Enqueue lỗi và recovery khi khởi động đi qua PostgreSQL.
        with postgres_connection() as conn:
            conn.execute(
                """UPDATE questions SET evaluation_status='FAILED',
                   payload=jsonb_set(payload, '{evaluation_status}', '"FAILED"'::jsonb)
                   WHERE id=%s""", (str(question_id),),
            )
        assert service.mark_evaluation_enqueue_error(
            str(question_id), expected_version=1, evaluator_model_code="fake-eval",
            message="provider down",
        )["evaluation_status"] == "ERROR"
        stale = service.enqueue_auto_evaluation(
            str(question_id), expected_version=1, requested_by_user_id=user["_id"],
            evaluator_model_code="fake-eval", model_snapshot=MODEL,
        )
        assert stale["attempt_no"] == 2
        with postgres_connection() as conn:
            conn.execute("UPDATE evaluation_jobs SET updated_at=now()-interval '3 hours' "
                         "WHERE id=%s", (stale["_id"],))
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        assert job_recovery._recover_postgres_evaluation_jobs(cutoff, "restart") == 1
        assert jobs.get(stale["_id"])["status"] == "STALE"
        assert questions.find_pair(question_id)[0]["evaluation_status"] == "STALE"
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
