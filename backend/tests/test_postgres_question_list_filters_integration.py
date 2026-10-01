"""Run with RUN_POSTGRES_INTEGRATION=1 and POSTGRES_DSN on a test database.

Expectations follow MongoQuestionRepository.list so the Reviewer queue behaves
the same after switching QUESTION_STORE to postgres.
"""

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from bson import ObjectId

from core.config import settings
from core.postgres import postgres_connection
from db.copy_business_data import projected_rows, upsert
from modules.questions.postgres_repository import PostgresQuestionRepository
from modules.users.postgres_repository import PostgresUserRepository


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="Requires an explicitly configured PostgreSQL test database",
)


def test_reviewer_queue_filters_counts_and_sorting(monkeypatch):
    monkeypatch.setattr(settings, "user_store", "postgres")
    monkeypatch.setattr(settings, "catalog_store", "postgres")
    monkeypatch.setattr(settings, "review_sla_hours", 24)
    suffix = uuid4().hex[:10]
    users = PostgresUserRepository()
    teacher, other, reviewer = (
        users.create({"firebase_uid": f"{name}-{suffix}", "email": f"{name}-{suffix}@example.test",
                      "display_name": name, "role": role})
        for name, role in (("t", "Teacher"), ("o", "Teacher"), ("r", "Reviewer"))
    )
    T, O, R = teacher["_id"], other["_id"], reviewer["_id"]
    now = datetime.now(timezone.utc)
    subject, chapter, clo, document = ObjectId(), ObjectId(), ObjectId(), ObjectId()
    q = {name: ObjectId() for name in ("q1", "q2", "q3", "q4", "q5")}
    v = {name: ObjectId() for name in q}
    review_id = ObjectId()
    repo = PostgresQuestionRepository()

    def question(name, *, code=None, review_status="PENDING", evaluation="PASSED",
                 submitted=None, assignment=None, quality=None, creator=T,
                 extra=None, classification=None, sources=(), clos=()):
        aggregate = {
            "_id": q[name], "schema_version": 2,
            "question_code": code or f"LQ-{suffix}-{name}", "subject_id": subject,
            "created_by_user_id": creator, "current_version": 1,
            "current_version_id": v[name], "approved_version_id": None,
            "lifecycle_status": "ACTIVE", "review_status": review_status,
            "evaluation_status": evaluation, "publication_status": "NOT_PUBLISHED",
            "review_assignment": assignment or {}, "quality_summary": quality or {},
            "review_submission": ({"submitted_at": now - submitted} if submitted else {}),
            "created_at": now, "updated_at": now, **(extra or {}),
        }
        version = {
            "_id": v[name], "question_id": q[name], "version": 1, "origin": "MANUAL",
            "content": f"Nội dung {name}", "question_data": {},
            "classification": {"subject": {"id": subject}, **(classification or {})},
            "clos": list(clos), "sources": list(sources),
            "content_hash": f"h-{name}-{suffix}", "created_by_user_id": creator,
            "created_at": now,
        }
        repo.create(aggregate, version)

    def ids(result):
        return [pair[0]["_id"] for pair in result[0]]

    def found(**filters):
        return set(ids(repo.list(1, 50, filters.pop("review_status", None),
                                 filters.pop("search", None), subject_id=str(subject),
                                 **filters)))

    try:
        with postgres_connection() as conn:
            for table, row in projected_rows("subjects", {
                "_id": subject, "subject_code": f"LQ-{suffix}", "subject_name": "Queue",
                "created_at": now, "updated_at": now,
            }):
                upsert(conn, table, row)
            for table, row in projected_rows("documents", {
                "_id": document, "title": "Queue doc", "original_filename": "q.pdf",
                "uploaded_by_user_id": T, "status": "READY", "current_version": 1,
                "created_at": now, "updated_at": now,
            }):
                upsert(conn, table, row)
        question("q1", evaluation="FAILED", submitted=timedelta(hours=72),
                 assignment={"status": "IN_REVIEW", "reviewer_user_id": R,
                             "lock_expires_at": now - timedelta(minutes=5)},
                 quality={"color": "RED", "overall_score": 0.3},
                 classification={"assessment_type": "SINGLE_CHOICE", "bloom": {"level": 2},
                                 "difficulty": "de", "chapter": {"id": chapter}},
                 sources=[{"chunk_id": "c1"}], clos=[{"id": clo}],
                 extra={})
        with postgres_connection() as conn:
            conn.execute(
                "UPDATE question_versions SET payload=jsonb_set(payload,'{document_id}',%s::jsonb) "
                "WHERE id=%s", (f'"{document}"', str(v["q1"])))
        question("q2", evaluation="NOT_STARTED", submitted=timedelta(hours=1), creator=O,
                 classification={"assessment_type": "TRUE_FALSE", "bloom": {"level": 3},
                                 "difficulty": "kho"},
                 extra={"secondary_review": {"status": "AWAITING_SECONDARY"},
                        "shared_with_user_ids": [T]})
        question("q3", review_status="APPROVED", submitted=timedelta(hours=5),
                 quality={"color": "GREEN", "overall_score": 0.9},
                 extra={"publication_status": "PUBLISHED", "latest_review_id": review_id})
        with postgres_connection() as conn:
            conn.execute("UPDATE questions SET approved_version_id=current_version_id WHERE id=%s",
                         (str(q["q3"]),))
            for table, row in projected_rows("question_reviews", {
                "_id": review_id, "question_id": q["q3"], "question_version_id": v["q3"],
                "reviewer_user_id": R, "decision": "APPROVED",
                "override": {"applied": True}, "reviewed_at": now,
            }):
                upsert(conn, table, row)
        question("q4", code=f"SPECIAL_%-{suffix}",
                 assignment={"status": "ASSIGNED", "reviewer_user_id": R,
                             "lock_expires_at": now + timedelta(hours=5)},
                 quality={"color": "GREEN", "overall_score": 0.8})
        question("q5", submitted=timedelta(hours=30),
                 quality={"color": "GREEN", "overall_score": 0.85})
        q1, q2, q3, q4, q5 = (q[name] for name in ("q1", "q2", "q3", "q4", "q5"))

        pending, total, counts = repo.list(1, 50, "PENDING", None, subject_id=str(subject),
                                           include_status_counts=True)
        assert total == 4 and {pair[0]["_id"] for pair in pending} == {q1, q2, q4, q5}
        assert counts == {"PENDING": 4, "APPROVED": 1}
        assert found(review_status="PROCESSED") == {q3}
        assert found(evaluation_status="NOT_STARTED,FAILED") == {q1, q2}
        assert found(assignment_status="UNASSIGNED") == {q2, q3, q5}
        assert found(assignment_status="IN_REVIEW", assigned_reviewer_user_id=R) == {q1}
        assert found(assigned_reviewer_user_id=R) == {q1, q4}
        assert found(quality_color="red") == {q1}
        assert found(min_score=0.75) == {q3, q4, q5}
        assert found(overdue_at=now) == {q1}
        assert found(secondary_status="AWAITING_SECONDARY") == {q2}
        assert found(override_only=True) == {q3}
        assert found(submitted_from=now - timedelta(hours=10)) == {q2, q3}
        assert found(submitted_to=now - timedelta(hours=10)) == {q1, q5}
        assert found(approved_current_only=True) == {q3}
        assert found(owner_user_id=T) == {q1, q3, q4, q5}
        assert found(visible_to_user_id=T) == {q1, q2, q3, q4, q5}
        assert found(visible_to_user_id=O) == {q2}
        assert found(creator_user_id=O) == {q2}
        assert found(question_type="true_false") == {q2}
        assert found(bloom_level=2) == {q1}
        assert found(document_id=str(document)) == {q1}
        assert found(chapter_id=str(chapter)) == {q1}
        assert found(clo_id=str(clo)) == {q1}
        assert found(difficulty="kho") == {q2}
        assert found(source_presence="WITH_SOURCE") == {q1}
        assert found(source_presence="MISSING_SOURCE") == {q2, q3, q4, q5}
        # Wildcards in the search text are matched literally.
        assert found(search="SPECIAL_%") == {q4}
        assert found(search="%") == {q4}
        assert found(search="nội dung q2") == {q2}

        def order(sort_by):
            return ids(repo.list(1, 50, "PENDING", None, subject_id=str(subject), sort_by=sort_by))

        assert order("oldest") == [q4, q1, q5, q2]
        assert order("newest") == [q2, q5, q1, q4]
        assert order("ai_lowest") == [q2, q1, q4, q5]
        assert order("priority") == [q1, q5, q2, q4]
        monkeypatch.setattr(settings, "review_sla_hours", 48)
        assert order("priority") == [q1, q2, q4, q5]
        assert ids(repo.list(2, 2, "PENDING", None, subject_id=str(subject),
                             sort_by="oldest")) == [q5, q2]
        with pytest.raises(ValueError):
            repo.list(1, 10, None, None, sort_by="random")
    finally:
        keys = [str(item) for item in q.values()]
        with postgres_connection() as conn:
            conn.execute("DELETE FROM question_reviews WHERE id=%s", (str(review_id),))
            conn.execute("UPDATE questions SET current_version_id=NULL, approved_version_id=NULL "
                         "WHERE id=ANY(%s)", (keys,))
            conn.execute("DELETE FROM question_versions WHERE question_id=ANY(%s)", (keys,))
            conn.execute("DELETE FROM questions WHERE id=ANY(%s)", (keys,))
            conn.execute("DELETE FROM document_subjects WHERE document_id=%s", (str(document),))
            conn.execute("DELETE FROM documents WHERE id=%s", (str(document),))
            conn.execute("DELETE FROM subjects WHERE id=%s", (str(subject),))
            conn.execute("DELETE FROM users WHERE id=ANY(%s)", ([str(T), str(O), str(R)],))
