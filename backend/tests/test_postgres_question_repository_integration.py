"""Run with RUN_POSTGRES_INTEGRATION=1 and POSTGRES_DSN on a test database."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from bson import ObjectId

from core.postgres import postgres_connection
from db.copy_business_data import projected_rows, upsert
from modules.questions.postgres_repository import PostgresQuestionRepository
from modules.questions.repository import serialize_question
from modules.users.postgres_repository import PostgresUserRepository


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="Requires an explicitly configured PostgreSQL test database",
)


def test_question_versions_submit_sharing_and_archive_are_transactional():
    suffix = uuid4().hex[:12]
    now = datetime.now(timezone.utc)
    user = PostgresUserRepository().create({
        "firebase_uid": f"question-{suffix}",
        "email": f"question-{suffix}@example.test",
        "display_name": "Teacher", "role": "Teacher",
    })
    subject_id = ObjectId()
    with postgres_connection() as conn:
        for table, row in projected_rows("subjects", {
            "_id": subject_id, "subject_code": f"Q-{suffix}",
            "subject_name": "Question subject", "created_at": now, "updated_at": now,
        }):
            upsert(conn, table, row)
    question_id, version_id = ObjectId(), ObjectId()
    aggregate = {
        "_id": question_id, "schema_version": 2,
        "question_code": f"Q-{suffix}", "subject_id": subject_id,
        "created_by_user_id": user["_id"],
        "current_version": 1, "current_version_id": version_id,
        "approved_version_id": None, "lifecycle_status": "ACTIVE",
        "review_status": "DRAFT", "evaluation_status": "NOT_STARTED",
        "publication_status": "NOT_PUBLISHED",
        "review_assignment": {"status": "UNASSIGNED"},
        "quality_summary": {}, "review_submission": {},
        "shared_scope": "PRIVATE", "shared_with_user_ids": [],
        "created_at": now, "updated_at": now,
    }
    version = {
        "_id": version_id, "question_id": question_id, "version": 1,
        "origin": "MANUAL", "content": "Câu hỏi một",
        "question_data": {"options": {"A": "đúng"}, "correct_answer": "A"},
        "classification": {"subject": {"id": subject_id}},
        "clos": [], "sources": [], "content_hash": f"hash-{suffix}-1",
        "created_by_user_id": user["_id"], "generation_run_id": None,
        "created_at": now,
    }
    repository = PostgresQuestionRepository()
    try:
        repository.create(aggregate, version)
        found = repository.find_pair(question_id)
        assert found[0]["current_version_id"] == version_id
        assert found[1]["content"] == "Câu hỏi một"
        assert found[1]["classification"]["subject"]["id"] == subject_id
        assert serialize_question(*found)["id"] == str(question_id)

        next_pair = repository.create_version(
            question_id, 1, {"content": "Câu hỏi hai",
                             "content_hash": f"hash-{suffix}-2"},
        )
        assert next_pair[0]["current_version"] == 2
        assert next_pair[1]["version"] == 2
        with pytest.raises(RuntimeError, match="VERSION_CONFLICT"):
            repository.create_version(question_id, 1, {"content": "stale"})
        assert [item["version"] for item in repository.list_versions(question_id)] == [2, 1]
        assert repository.list_versions(question_id)[1]["content"] == "Câu hỏi một"

        submitted = repository.update_review_status(
            question_id, {"DRAFT"}, "PENDING",
            review_submission={"submitted_by_user_id": user["_id"]},
        )
        assert submitted[0]["review_status"] == "PENDING"
        assert submitted[0]["review_submission"]["submitted_by_user_id"] == user["_id"]
        assert repository.update_review_status(question_id, {"DRAFT"}, "PENDING") is None

        shared = repository.update_sharing(question_id, {
            "shared_scope": "SUBJECT", "shared_with_user_ids": [user["_id"]],
        })
        assert shared[0]["shared_scope"] == "SUBJECT"
        assert shared[0]["shared_with_user_ids"] == [user["_id"]]
        listed, total, status_counts = repository.list(
            1, 10, "PENDING", "Câu hỏi hai", subject_id=str(subject_id),
            question_type=None, visible_to_user_id=user["_id"],
            include_status_counts=True,
        )
        assert total == 1 and listed[0][0]["_id"] == question_id
        assert status_counts == {"PENDING": 1}
        assert repository.list(1, 10, "APPROVED", None)[1] == 0
        assert repository.list(1, 10, None, None, source_presence="MISSING_SOURCE")[1] == 1
        with postgres_connection() as conn:
            assert conn.execute("SELECT count(*) AS n FROM question_versions WHERE question_id=%s",
                                (str(question_id),)).fetchone()["n"] == 2
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(
                repository.create_version, question_id, 2,
                {"content": f"Đồng thời {index}",
                 "content_hash": f"hash-{suffix}-race-{index}"},
            ) for index in (1, 2)]
            outcomes = []
            for future in futures:
                try:
                    outcomes.append(future.result())
                except RuntimeError as exc:
                    outcomes.append(str(exc))
        assert sum(isinstance(result, tuple) for result in outcomes) == 1
        assert outcomes.count("VERSION_CONFLICT") == 1
        assert repository.find_pair(question_id)[0]["current_version"] == 3
        assert [item["version"] for item in repository.list_versions(question_id)] == [3, 2, 1]
        assert repository.archive(question_id) is True
        assert repository.find_pair(question_id) is None
        assert repository.archive(question_id) is False
        assert len(repository.list_versions(question_id)) == 3
    finally:
        with postgres_connection() as conn:
            conn.execute("UPDATE questions SET current_version_id=NULL, approved_version_id=NULL "
                         "WHERE id=%s", (str(question_id),))
            conn.execute("DELETE FROM question_versions WHERE question_id=%s",
                         (str(question_id),))
            conn.execute("DELETE FROM questions WHERE id=%s", (str(question_id),))
            conn.execute("DELETE FROM subjects WHERE id=%s", (str(subject_id),))
            conn.execute("DELETE FROM users WHERE id=%s", (str(user["_id"]),))
