"""Run with RUN_POSTGRES_INTEGRATION=1 and POSTGRES_DSN on a test database."""

import os
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from bson import ObjectId

from core.audit import record_audit_event
from core.config import settings
from core.postgres import postgres_connection
from db.copy_business_data import projected_rows, upsert
from modules.admin.overview_service import AdminOverviewService
from modules.catalog.service import CatalogService
from modules.questions.postgres_repository import PostgresQuestionRepository
from modules.users.postgres_repository import PostgresUserRepository


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="Requires an explicitly configured PostgreSQL test database",
)


def test_overview_catalog_user_stats_and_audit_read_postgres(monkeypatch):
    for key in ("user_store", "catalog_store", "document_store", "question_store",
                "exam_store", "audit_store", "ai_config_store", "generation_store",
                "moodle_target_store", "llm_slot_store", "notification_store"):
        monkeypatch.setattr(settings, key, "postgres")
    suffix = uuid4().hex[:12]
    users = PostgresUserRepository()
    teacher = users.create({"firebase_uid": f"c-{suffix}", "email": f"c-{suffix}@example.test",
                            "display_name": "Counter", "role": "Teacher"})
    now = datetime.now(timezone.utc)
    subject_id, chapter_id, clo_id = ObjectId(), ObjectId(), ObjectId()
    document_id = ObjectId()
    q_green, q_pending = ObjectId(), ObjectId()
    v_green, v_pending = ObjectId(), ObjectId()
    questions = PostgresQuestionRepository()
    try:
        with postgres_connection() as conn:
            for table, row in projected_rows("subjects", {
                "_id": subject_id, "subject_code": f"CN-{suffix}",
                "subject_name": "Counts", "created_at": now, "updated_at": now,
            }):
                upsert(conn, table, row)
            for table, row in projected_rows("documents", {
                "_id": document_id, "title": "Counted", "original_filename": "c.pdf",
                "subject_id": subject_id, "chapter_id": chapter_id,
                "uploaded_by_user_id": teacher["_id"], "status": "READY",
                "current_version": 1, "created_at": now, "updated_at": now,
            }):
                upsert(conn, table, row)
        for qid, vid, review_status, color in (
            (q_green, v_green, "APPROVED", "GREEN"),
            (q_pending, v_pending, "PENDING", None),
        ):
            questions.create({
                "_id": qid, "schema_version": 2, "question_code": f"CN-{qid}",
                "subject_id": subject_id, "created_by_user_id": teacher["_id"],
                "document_id": document_id,
                "current_version": 1, "current_version_id": vid,
                "approved_version_id": vid if review_status == "APPROVED" else None,
                "lifecycle_status": "ACTIVE", "review_status": review_status,
                "evaluation_status": "PASSED" if color else "NOT_STARTED",
                "publication_status": "NOT_PUBLISHED", "review_assignment": {},
                "quality_summary": {"color": color} if color else {},
                "created_at": now, "updated_at": now,
            }, {
                "_id": vid, "question_id": qid, "version": 1, "origin": "MANUAL",
                "content": f"Câu {qid}", "document_id": document_id,
                "question_data": {}, "clos": [{"id": clo_id}], "sources": [],
                "classification": {"subject": {"id": subject_id},
                                   "chapter": {"id": chapter_id}},
                "content_hash": f"h-{qid}", "created_by_user_id": teacher["_id"],
                "created_at": now,
            })

        overview = AdminOverviewService(SimpleNamespace())
        user_summary = overview._user_summary()
        assert user_summary["teachers"] >= 1 and user_summary["active"] >= 1
        question_summary = overview._question_summary()
        assert question_summary["total"] >= 2
        assert question_summary["pending"] >= 1 and question_summary["approved"] >= 1
        assert question_summary["quality"]["green"] >= 1
        assert question_summary["quality"]["not_evaluated"] >= 1

        # With every store on PostgreSQL, the full overview must not touch Mongo.
        full = overview.overview()
        assert full["questions"]["pending"] >= 1 and full["users"]["total"] >= 1

        usage = CatalogService(SimpleNamespace())._usage_counts({
            "_id": subject_id,
            "chapters": [{"_id": chapter_id}],
            "learning_outcomes": [{"_id": clo_id}],
        })
        assert usage["subject"] == {"documents": 1, "questions": 2, "exams": 0}
        assert usage["chapters"][str(chapter_id)] == {"documents": 1, "questions": 2, "exams": 0}
        assert usage["learning_outcomes"][str(clo_id)] == {"questions": 2}

        assert users.get_stats(teacher["_id"]) == {
            "documents_count": 1, "questions_count": 2, "pending_questions_count": 1,
        }
        assert {item["_id"] for item in users.get_calendar_questions(teacher["_id"])} == {
            q_green, q_pending}
        assert users.get_document_ids_with_questions([document_id, ObjectId()]) == {
            str(document_id)}

        record_audit_event(action="admin.test_event", entity_type="subject",
                           entity_id=str(subject_id), actor_user_id=teacher["_id"],
                           actor_role="Teacher", changes=[], metadata={"k": "v"})
        with postgres_connection() as conn:
            row = conn.execute("SELECT metadata FROM audit_logs WHERE action='admin.test_event' "
                               "AND entity_id=%s", (str(subject_id),)).fetchone()
        assert row["metadata"] == {"k": "v"}
    finally:
        with postgres_connection() as conn:
            conn.execute("DELETE FROM audit_logs WHERE actor_user_id=%s", (str(teacher["_id"]),))
            ids = [str(q_green), str(q_pending)]
            conn.execute("UPDATE questions SET current_version_id=NULL, approved_version_id=NULL "
                         "WHERE id=ANY(%s)", (ids,))
            conn.execute("DELETE FROM question_versions WHERE question_id=ANY(%s)", (ids,))
            conn.execute("DELETE FROM questions WHERE id=ANY(%s)", (ids,))
            conn.execute("DELETE FROM document_subjects WHERE document_id=%s", (str(document_id),))
            conn.execute("DELETE FROM documents WHERE id=%s", (str(document_id),))
            conn.execute("DELETE FROM subjects WHERE id=%s", (str(subject_id),))
            conn.execute("DELETE FROM users WHERE id=%s", (str(teacher["_id"]),))
