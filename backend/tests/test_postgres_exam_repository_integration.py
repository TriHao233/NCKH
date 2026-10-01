"""Run with RUN_POSTGRES_INTEGRATION=1 and POSTGRES_DSN on a test database."""

import os
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from bson import ObjectId

from core.config import settings
from core.dependencies import CurrentUser
from core.postgres import postgres_connection
from db.copy_business_data import projected_rows, upsert
from modules.admin.moodle_service import MoodleTargetService
from modules.exams import service as exam_module
from modules.exams.postgres_repository import PostgresExamRepository
from modules.exams.schemas import (
    AddQuestionsManualRequest, ExamCreateRequest, ExamHeaderConfig, ExamMatrixRequest,
    ExamStatusUpdateRequest, ExamVariantCreateRequest,
)
from modules.notifications.service import NotificationService
from modules.questions.postgres_repository import PostgresQuestionRepository
from modules.users.postgres_repository import PostgresUserRepository


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="Requires an explicitly configured PostgreSQL test database",
)


def _actor(user: dict, role: str) -> CurrentUser:
    return CurrentUser(id=user["_id"], firebase_uid="", email=user["email"], role=role,
                       is_active=True, permissions=())


def test_exams_variants_and_moodle_admin_use_postgres(monkeypatch):
    for key in ("user_store", "catalog_store", "question_store", "exam_store",
                "notification_store", "moodle_target_store"):
        monkeypatch.setattr(settings, key, "postgres")
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(exam_module, "get_database", lambda: SimpleNamespace())
    suffix = uuid4().hex[:12]
    users = PostgresUserRepository()
    teacher, other, admin = (
        users.create({"firebase_uid": f"{name}-{suffix}", "email": f"{name}-{suffix}@example.test",
                      "display_name": name, "role": role})
        for name, role in (("owner", "Teacher"), ("other", "Teacher"), ("admin", "Admin"))
    )
    owner, stranger, admin_actor = (_actor(teacher, "Teacher"), _actor(other, "Teacher"),
                                    _actor(admin, "Admin"))
    now = datetime.now(timezone.utc)
    subject_id, chapter_id = ObjectId(), ObjectId()
    question_id, version_id = ObjectId(), ObjectId()
    questions = PostgresQuestionRepository()
    exam_ids: list[str] = []
    try:
        with postgres_connection() as conn:
            for table, row in projected_rows("subjects", {
                "_id": subject_id, "subject_code": f"EX-{suffix}",
                "subject_name": "Exams", "created_at": now, "updated_at": now,
            }):
                upsert(conn, table, row)
        questions.create({
            "_id": question_id, "schema_version": 2, "question_code": f"EX-{suffix}",
            "subject_id": subject_id, "created_by_user_id": teacher["_id"],
            "current_version": 1, "current_version_id": version_id,
            "approved_version_id": version_id, "lifecycle_status": "ACTIVE",
            "review_status": "APPROVED", "evaluation_status": "PASSED",
            "publication_status": "NOT_PUBLISHED", "review_assignment": {},
            "created_at": now, "updated_at": now,
        }, {
            "_id": version_id, "question_id": question_id, "version": 1, "origin": "MANUAL",
            "content": "2 + 2 = ?",
            "question_data": {"question_type": "SINGLE_CHOICE",
                              "options": {"A": "3", "B": "4", "C": "5", "D": "6"},
                              "correct_answer": "B"},
            "classification": {"subject": {"id": subject_id},
                               "chapter": {"id": chapter_id},
                               "assessment_type": "SINGLE_CHOICE",
                               "bloom": {"level": 1}, "difficulty": "de"},
            "clos": [], "sources": [], "content_hash": f"hash-{suffix}",
            "created_by_user_id": teacher["_id"], "created_at": now,
        })
        exams = exam_module.get_exam_service()
        variants = exam_module.get_exam_variant_service()
        assert isinstance(exams.repository, PostgresExamRepository)
        assert isinstance(exams.question_repository, PostgresQuestionRepository)

        created = exams.create_exam(ExamCreateRequest(
            name="Giữa kỳ", exam_title="Kiểm tra", subject_id=str(subject_id),
            question_count=1,
            header=ExamHeaderConfig(
                school_name="CTU", exam_name="Kiểm tra", subject_name="Exams",
            )), teacher["_id"])
        exam_ids.append(created["id"])
        with pytest.raises(PermissionError):
            exams.get_exam(created["id"], stranger)
        pool = exams.question_pool(created["id"], owner)
        assert [item["id"] for item in pool["items"]] == [str(question_id)]
        added = exams.add_questions_manual(
            created["id"], AddQuestionsManualRequest(question_ids=[str(question_id)]), owner)
        assert added["questions"][0]["version_id"] == str(version_id)
        assert exams.question_pool(created["id"], owner)["items"][0]["in_exam"] is True
        assert exams.list_exams(1, 10, owner)["total"] == 1
        assert exams.list_exams(1, 10, stranger)["total"] == 0
        assert [str(item["_id"]) for item in
                PostgresExamRepository.open_exams_using_question(question_id)] == [created["id"]]
        notified = NotificationService(None).notify_exam_owners_question_reopened(
            question_id=question_id, question_code=f"EX-{suffix}", actor_user_id=admin["_id"])
        assert len(notified) == 1

        exams.update_status(created["id"], ExamStatusUpdateRequest(status="READY"), owner)
        final = exams.update_status(created["id"], ExamStatusUpdateRequest(status="FINALIZED"), owner)
        assert final["status"] == "FINALIZED"
        assert PostgresExamRepository.open_exams_using_question(question_id) == []

        variant = variants.create_variant(
            created["id"], ExamVariantCreateRequest(exam_code="101", shuffle=True), owner)
        assert variant["answer_key"][str(question_id)] in {"A", "B", "C", "D"}
        with pytest.raises(ValueError, match="đã tồn tại"):
            variants.create_variant(created["id"], ExamVariantCreateRequest(exam_code="101"), owner)
        assert [item["id"] for item in variants.list_variants(created["id"], owner)] == [variant["id"]]
        preview = variants.build_preview(created["id"], variant["id"], owner)
        assert preview["questions"][0]["content"] == "2 + 2 = ?"
        assert exams.get_exam(created["id"], owner)["variant_count"] == 1
        with pytest.raises(ValueError):
            exams.delete_exam(created["id"], owner)

        clone = exams.duplicate_exam(created["id"], owner)
        exam_ids.append(clone["id"])
        assert clone["status"] == "DRAFT" and len(clone["questions"]) == 1
        matrix = exams.save_matrix(clone["id"], ExamMatrixRequest(cells=[{
            "chapter_id": str(chapter_id), "cognitive_level": "nhan_biet",
            "difficulty": "de", "count": 1}]), owner)
        assert matrix["matrix"][0]["chapter_id"] == str(chapter_id)
        assert exams.matrix_availability(clone["id"], owner)[0]["available"] == 1
        assert PostgresExamRepository.count(subject_id=subject_id) == 2
        assert PostgresExamRepository.count(chapter_id=chapter_id) == 1
        exams.remove_question(clone["id"], str(question_id), owner)
        with postgres_connection() as conn:
            assert conn.execute("SELECT count(*) AS n FROM exam_questions WHERE exam_id=%s",
                                (clone["id"],)).fetchone()["n"] == 0
        exams.delete_exam(clone["id"], owner)
        assert exams.repository.find(clone["id"]) is None

        # Admin Moodle publications: list, summary and retry of a failed record.
        moodle = MoodleTargetService(SimpleNamespace())
        from modules.questions.workflow_schemas import MoodlePublicationRequest
        from modules.questions.workflow_service import QuestionWorkflowService
        published = QuestionWorkflowService(SimpleNamespace()).publish_to_moodle(
            str(question_id), MoodlePublicationRequest(expected_version=1), admin["_id"], "Admin")
        with postgres_connection() as conn:
            conn.execute(
                """UPDATE moodle_publications SET status='FAILED',
                   payload=payload || '{"status":"FAILED","error":{"message":"timeout"}}'::jsonb
                   WHERE id=%s""", (published["_id"],))
        listed = moodle.list_publications(page=1, page_size=10, search="timeout")
        assert [item["id"] for item in listed["items"]] == [published["_id"]]
        assert listed["summary"]["failed"] == 1 and listed["summary"]["simulated"] == 1
        assert moodle.list_publications(page=1, page_size=10, status="published")["total"] == 0
        retried = moodle.retry_publication(published["_id"], admin_actor)
        assert retried["status"] == "PUBLISHED" and retried["attempt_no"] == 2
        with postgres_connection() as conn:
            assert conn.execute(
                "SELECT count(*) AS n FROM audit_logs WHERE entity_type='moodle_publication' "
                "AND entity_id=%s", (published["_id"],)).fetchone()["n"] == 1
    finally:
        user_ids = [str(teacher["_id"]), str(other["_id"]), str(admin["_id"])]
        with postgres_connection() as conn:
            conn.execute("DELETE FROM notifications WHERE recipient_user_id=ANY(%s)", (user_ids,))
            conn.execute("DELETE FROM audit_logs WHERE actor_user_id=ANY(%s) OR entity_id=%s",
                         (user_ids, str(question_id)))
            conn.execute("DELETE FROM exam_variants WHERE exam_id=ANY(%s)", (exam_ids,))
            conn.execute("DELETE FROM exam_questions WHERE exam_id=ANY(%s)", (exam_ids,))
            conn.execute("DELETE FROM exams WHERE id=ANY(%s)", (exam_ids,))
            conn.execute("DELETE FROM moodle_publications WHERE question_id=%s", (str(question_id),))
            conn.execute("UPDATE questions SET current_version_id=NULL, approved_version_id=NULL "
                         "WHERE id=%s", (str(question_id),))
            conn.execute("DELETE FROM question_versions WHERE question_id=%s", (str(question_id),))
            conn.execute("DELETE FROM questions WHERE id=%s", (str(question_id),))
            conn.execute("DELETE FROM subjects WHERE id=%s", (str(subject_id),))
            conn.execute("DELETE FROM users WHERE id=ANY(%s)", (user_ids,))
