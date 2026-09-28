"""Run with RUN_POSTGRES_INTEGRATION=1 and POSTGRES_DSN on a test database."""

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from bson import ObjectId
from fastapi import BackgroundTasks

from core.config import settings
from core.dependencies import CurrentUser
from core.postgres import postgres_connection
from db.copy_business_data import projected_rows, upsert
from modules.admin.job_metrics import collect_job_metrics
from modules.admin.jobs_service import AdminJobService
from modules.admin.overview_service import AdminOverviewService
from modules.questions.postgres_evaluation_jobs import PostgresEvaluationJobs
from modules.questions.postgres_repository import PostgresQuestionRepository
from modules.questions.workflow_service import QuestionWorkflowService
from modules.users.postgres_repository import PostgresUserRepository


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="Requires an explicitly configured PostgreSQL test database",
)

MODEL = {"model_code": "admin-eval", "model_name": "Admin eval", "runtime": "TEST"}


def test_admin_lists_cancels_retries_and_measures_postgres_evaluation_jobs(monkeypatch):
    for key in ("user_store", "catalog_store", "question_store", "document_store",
                "llm_slot_store"):
        monkeypatch.setattr(settings, key, "postgres")
    monkeypatch.setattr(settings, "evaluation_fallback_provider", "")
    monkeypatch.setattr(QuestionWorkflowService, "_build_evaluation_prompt",
                        lambda *_a, **_k: ("prompt", {"key": "quality"}, []))
    monkeypatch.setattr(QuestionWorkflowService, "_policy",
                        lambda _self: {"_id": None, "policy_name": "test", "version": 1})
    suffix = uuid4().hex[:12]
    users = PostgresUserRepository()
    teacher = users.create({"firebase_uid": f"t-{suffix}", "email": f"t-{suffix}@example.test",
                            "display_name": "Teacher Admin Jobs", "role": "Teacher"})
    admin = users.create({"firebase_uid": f"a-{suffix}", "email": f"a-{suffix}@example.test",
                          "display_name": "Admin", "role": "Admin"})
    admin_actor = CurrentUser(id=admin["_id"], firebase_uid="", email=admin["email"],
                              role="Admin", is_active=True, permissions=())
    now = datetime.now(timezone.utc)
    subject_id, question_id, version_id = ObjectId(), ObjectId(), ObjectId()
    failed_id, queued_id, legacy_id = ObjectId(), ObjectId(), ObjectId()
    repository = PostgresQuestionRepository()
    jobs = PostgresEvaluationJobs()
    try:
        with postgres_connection() as conn:
            for table, row in projected_rows("subjects", {
                "_id": subject_id, "subject_code": f"AJ-{suffix}",
                "subject_name": "Admin jobs", "created_at": now, "updated_at": now,
            }):
                upsert(conn, table, row)
        repository.create({
            "_id": question_id, "schema_version": 2, "question_code": f"AJ-{suffix}",
            "subject_id": subject_id, "created_by_user_id": teacher["_id"],
            "current_version": 1, "current_version_id": version_id,
            "approved_version_id": None, "lifecycle_status": "ACTIVE",
            "review_status": "PENDING", "evaluation_status": "QUEUED",
            "publication_status": "NOT_PUBLISHED",
            "review_assignment": {"status": "UNASSIGNED"},
            "quality_summary": {"latest_evaluation_job_id": queued_id, "color": "RED"},
            "created_at": now, "updated_at": now,
        }, {
            "_id": version_id, "question_id": question_id, "version": 1,
            "origin": "MANUAL", "content": "Câu hỏi Admin jobs",
            "question_data": {"options": {"A": "đúng"}, "correct_answer": "A"},
            "classification": {"subject": {"id": subject_id}},
            "clos": [], "sources": [], "content_hash": f"hash-{suffix}",
            "created_by_user_id": teacher["_id"], "created_at": now,
        })
        base = {"question_id": question_id, "question_version_id": version_id,
                "question_version": 1, "requested_by_user_id": teacher["_id"],
                "evaluator_model_code": "admin-eval", "model_snapshot": MODEL,
                "duration_ms": 1200, "queued_at": now, "created_at": now}
        with postgres_connection() as conn:
            for job in (
                {**base, "_id": failed_id, "status": "ERROR", "attempt_no": 1,
                 "error": {"message": "provider down"}, "dead_lettered_at": now,
                 "updated_at": now - timedelta(minutes=3)},
                {**base, "_id": legacy_id, "status": "STALE", "attempt_no": 2,
                 "error": {"message": "Cancelled by admin old@example.test"},
                 "updated_at": now - timedelta(minutes=2)},
                {**base, "_id": queued_id, "status": "QUEUED", "attempt_no": 3,
                 "dedupe_key": f"aj-{suffix}", "updated_at": now - timedelta(minutes=1)},
            ):
                for table, row in projected_rows("evaluation_jobs", job):
                    upsert(conn, table, row)

        service = AdminJobService(SimpleNamespace())
        listed = service.list_jobs(page=1, page_size=20, job_kind="evaluation",
                                   user_id=str(teacher["_id"]))
        assert listed["total"] == 3
        by_id = {item["id"]: item for item in listed["items"]}
        assert by_id[str(legacy_id)]["status"] == "CANCELLED"
        assert by_id[str(queued_id)]["entity"]["label"] == f"AJ-{suffix}"
        assert by_id[str(queued_id)]["entity"]["subject_label"] == "Admin jobs"
        assert by_id[str(queued_id)]["actor_user_name"] == "Teacher Admin Jobs"
        cancelled = service.list_jobs(page=1, page_size=20, job_kind="evaluation",
                                      status="cancelled", user_id=str(teacher["_id"]))
        assert [item["id"] for item in cancelled["items"]] == [str(legacy_id)]
        assert service.list_jobs(page=1, page_size=20, job_kind="evaluation",
                                 status="stale", user_id=str(teacher["_id"]))["total"] == 0

        metrics = collect_job_metrics(MagicMock())["queues"]["evaluation"]
        assert metrics["queued"] >= 1 and metrics["dead_lettered"] >= 1

        groups: dict = {}
        AdminOverviewService(SimpleNamespace())._collect_evaluation_model_performance(
            groups, now - timedelta(days=1))
        assert groups["evaluation:admin-eval"]["total"] == 3

        result = service.cancel_job("evaluation", str(queued_id), admin_actor)
        assert result["job"]["status"] == "CANCELLED"
        with pytest.raises(ValueError):
            service.cancel_job("evaluation", str(queued_id), admin_actor)
        question = repository.find_pair(question_id)[0]
        assert question["evaluation_status"] == "NOT_STARTED"
        assert "color" not in question["quality_summary"]

        retried = service.retry_job("evaluation", str(failed_id), BackgroundTasks(), admin_actor)
        assert retried["already_queued"] is False
        new_id = retried["job"]["_id"]
        assert jobs.get(new_id)["trigger"] == "ADMIN_RETRY"
        again = service.retry_job("evaluation", str(failed_id), BackgroundTasks(), admin_actor)
        assert again["already_queued"] is True and again["job"]["_id"] == new_id
        with postgres_connection() as conn:
            actions = {row["action"] for row in conn.execute(
                "SELECT action FROM audit_logs WHERE entity_type='evaluation' AND entity_id=ANY(%s)",
                ([str(failed_id), str(queued_id)],),
            ).fetchall()}
        assert actions == {"admin.job_retry", "admin.job_cancel"}
    finally:
        with postgres_connection() as conn:
            conn.execute("DELETE FROM audit_logs WHERE entity_id=ANY(%s)",
                         ([str(question_id), str(failed_id), str(queued_id)],))
            conn.execute("DELETE FROM evaluation_jobs WHERE question_id=%s", (str(question_id),))
            conn.execute("UPDATE questions SET current_version_id=NULL WHERE id=%s",
                         (str(question_id),))
            conn.execute("DELETE FROM question_versions WHERE question_id=%s",
                         (str(question_id),))
            conn.execute("DELETE FROM questions WHERE id=%s", (str(question_id),))
            conn.execute("DELETE FROM subjects WHERE id=%s", (str(subject_id),))
            conn.execute("DELETE FROM users WHERE id=ANY(%s)",
                         ([str(teacher["_id"]), str(admin["_id"])],))
