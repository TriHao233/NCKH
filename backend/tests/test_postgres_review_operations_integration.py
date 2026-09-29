"""Run with RUN_POSTGRES_INTEGRATION=1 and POSTGRES_DSN on a test database."""

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from bson import ObjectId

from core.config import settings
from core.dependencies import CurrentUser
from core.postgres import postgres_connection
from db.copy_business_data import projected_rows, upsert
from modules.notifications.service import NotificationService
from modules.questions.postgres_repository import PostgresQuestionRepository
from modules.questions.workflow_schemas import (
    AutoAssignRequest, MoodlePublicationRequest, ReviewCreateRequest,
)
from modules.questions.workflow_service import QuestionWorkflowService
from modules.users.postgres_repository import PostgresUserRepository


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="Requires an explicitly configured PostgreSQL test database",
)


def _actor(user: dict, role: str) -> CurrentUser:
    return CurrentUser(id=user["_id"], firebase_uid="", email=user["email"], role=role,
                       is_active=True, permissions=("reviews.manage",))


def test_reviewer_operations_read_and_write_postgres(monkeypatch):
    for key in ("user_store", "catalog_store", "question_store", "notification_store",
                "review_policy_store", "moodle_target_store", "audit_store"):
        monkeypatch.setattr(settings, key, "postgres")
    monkeypatch.setattr(settings, "app_env", "development")
    suffix = uuid4().hex[:12]
    users = PostgresUserRepository()
    teacher, reviewer, admin = (
        users.create({"firebase_uid": f"{role}-{suffix}",
                      "email": f"{role}-{suffix}@example.test",
                      "display_name": role, "role": role})
        for role in ("Teacher", "Reviewer", "Admin")
    )
    now = datetime.now(timezone.utc)
    subject_id, question_id, version_id = ObjectId(), ObjectId(), ObjectId()
    repository = PostgresQuestionRepository()
    try:
        with postgres_connection() as conn:
            for table, row in projected_rows("subjects", {
                "_id": subject_id, "subject_code": f"R-{suffix}",
                "subject_name": "Review ops", "created_at": now, "updated_at": now,
            }):
                upsert(conn, table, row)
        repository.create({
            "_id": question_id, "schema_version": 2, "question_code": f"R-{suffix}",
            "subject_id": subject_id, "created_by_user_id": teacher["_id"],
            "current_version": 1, "current_version_id": version_id,
            "approved_version_id": None, "lifecycle_status": "ACTIVE",
            "review_status": "PENDING", "evaluation_status": "NOT_STARTED",
            "publication_status": "NOT_PUBLISHED",
            "review_assignment": {"status": "UNASSIGNED"}, "quality_summary": {},
            "review_submission": {"submitted_by_user_id": teacher["_id"],
                                  "submitted_at": now - timedelta(hours=72)},
            "created_at": now, "updated_at": now,
        }, {
            "_id": version_id, "question_id": question_id, "version": 1,
            "origin": "MANUAL", "content": "Thủ đô của Việt Nam là gì?",
            "question_data": {"question_type": "SINGLE_CHOICE",
                              "options": {"A": "Hà Nội", "B": "Huế"},
                              "correct_answer": "A"},
            "classification": {"subject": {"id": subject_id}},
            "clos": [], "sources": [], "content_hash": f"hash-{suffix}",
            "created_by_user_id": teacher["_id"], "created_at": now,
        })
        workflow = QuestionWorkflowService(SimpleNamespace())
        admin_actor, reviewer_actor = _actor(admin, "Admin"), _actor(reviewer, "Reviewer")

        result = workflow.auto_assign_reviews(
            AutoAssignRequest(question_ids=[str(question_id)]), admin_actor,
        )
        assert [item["reviewer_user_id"] for item in result["assigned"]] == [str(reviewer["_id"])]
        assert repository.held_reviews(active_at=now)[0]["_id"] == question_id

        assert workflow.release_assignments_for_reviewer(
            reviewer["_id"], None, "reviewer_deactivated") == 1
        assert repository.find_pair(question_id)[0]["review_assignment"]["status"] == "UNASSIGNED"
        with postgres_connection() as conn:
            audit = conn.execute(
                """SELECT payload FROM audit_logs WHERE entity_id=%s
                   AND action='QUESTION_REVIEW_RELEASED'""", (str(question_id),),
            ).fetchone()["payload"]
        assert audit["actor"]["service_name"] == "user_management"

        assert workflow.send_review_sla_reminders(now) == 1
        assert workflow.send_review_sla_reminders(now) == 0
        admin_notes = NotificationService(None).list(admin_actor, 1, 20)
        assert any(item["type"] == "QUESTION_REVIEW_SLA_BREACHED"
                   for item in admin_notes["items"])

        workflow.claim_review(str(question_id), reviewer_actor)
        review = workflow.review(
            str(question_id), ReviewCreateRequest(expected_version=1, decision="APPROVED"),
            reviewer_actor,
        )
        assert review["decision"] == "APPROVED"
        assert [item["_id"] for item in workflow.history(
            str(question_id), "reviews", admin_actor)] == [review["_id"]]
        assert workflow.history(str(question_id), "evaluations", admin_actor) == []
        assert repository.latest_review(repository.find_pair(question_id)[0])["_id"] == ObjectId(review["_id"])
        # APPROVED không cần báo gửi lại; db=None chứng minh không còn đọc Mongo.
        assert NotificationService(None).notify_question_resubmitted(
            question_id=question_id, previous_review_status="APPROVED",
            actor_user_id=teacher["_id"],
        ) == []

        request = MoodlePublicationRequest(expected_version=1)
        published = workflow.publish_to_moodle(str(question_id), request, admin["_id"], "Admin")
        assert published["status"] == "PUBLISHED"
        assert published["target"]["target_id"] is None
        again = workflow.publish_to_moodle(str(question_id), request, admin["_id"], "Admin")
        assert again["_id"] == published["_id"]
        assert [item["_id"] for item in workflow.history(
            str(question_id), "publications", admin_actor)] == [published["_id"]]
        assert repository.find_pair(question_id)[0]["publication_status"] == "PUBLISHED"

        suggestions = workflow.suggest_review_subjects(str(reviewer["_id"]))
        assert suggestions["items"][0]["subject_id"] == str(subject_id)
        assert suggestions["items"][0]["subject_code"] == f"R-{suffix}"

        dashboard = workflow.review_dashboard(admin_actor)
        assert dashboard["scope"] == "all_reviewers"
        assert dashboard["performance"]["reviews_30d"] >= 1
        assert dashboard["performance"]["duration_sample_size"] >= 1
        row = next(item for item in dashboard["reviewers"]
                   if item["user_id"] == str(reviewer["_id"]))
        assert row["reviews_30d"] == 1 and row["decisions"]["APPROVED"] == 1
        assert row["average_review_hours"] is not None
        mine = workflow.review_dashboard(reviewer_actor)
        assert mine["scope"] == "current_reviewer"
        assert mine["performance"]["reviews_30d"] == 1
        assert set(mine["workload"]) >= {"pending", "unassigned", "mine", "sla_breached"}
        assert any(item["subject_id"] == str(subject_id) for item in mine["subjects"])
    finally:
        user_ids = [str(teacher["_id"]), str(reviewer["_id"]), str(admin["_id"])]
        with postgres_connection() as conn:
            conn.execute("DELETE FROM notifications WHERE recipient_user_id=ANY(%s)", (user_ids,))
            conn.execute("DELETE FROM audit_logs WHERE entity_id=%s OR actor_user_id=ANY(%s)",
                         (str(question_id), user_ids))
            for table in ("moodle_publications", "question_reviews", "question_review_drafts"):
                conn.execute(f"DELETE FROM {table} WHERE question_id=%s", (str(question_id),))
            conn.execute("UPDATE questions SET current_version_id=NULL WHERE id=%s",
                         (str(question_id),))
            conn.execute("DELETE FROM question_versions WHERE question_id=%s",
                         (str(question_id),))
            conn.execute("DELETE FROM questions WHERE id=%s", (str(question_id),))
            conn.execute("DELETE FROM subjects WHERE id=%s", (str(subject_id),))
            conn.execute("DELETE FROM users WHERE id=ANY(%s)", (user_ids,))
