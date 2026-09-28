"""Run with RUN_POSTGRES_INTEGRATION=1 and POSTGRES_DSN on a test database."""

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from bson import ObjectId

from core.config import settings
from core.postgres import postgres_connection
from modules.questions.workflow_service import QuestionWorkflowService
from modules.users.postgres_repository import PostgresUserRepository
from modules.users.store import (
    active_admin_ids, find_user_record, review_candidate_users, users_by_ids,
)


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1" or not settings.postgres_dsn,
    reason="Requires an explicitly configured PostgreSQL test database",
)


def test_question_workflow_reads_reviewer_scope_and_permissions_from_postgres(monkeypatch):
    monkeypatch.setattr(settings, "user_store", "postgres")
    suffix = uuid4().hex[:12]
    subject_id = ObjectId()
    users = PostgresUserRepository()
    created = []
    try:
        for index, role, data in (
            (1, "Reviewer", {"review_subject_ids": [subject_id]}),
            (2, "Reviewer", {"permission_revokes": ["reviews.manage"]}),
            (3, "Admin", {}),
        ):
            created.append(users.create({
                "firebase_uid": f"reviewer-{suffix}-{index}",
                "email": f"reviewer-{suffix}-{index}@example.test",
                "display_name": f"User {index}", "role": role, **data,
            }))
        database = SimpleNamespace()
        workflow = QuestionWorkflowService(database)
        selected = workflow._find_assignable_reviewer(str(created[0]["_id"]))
        assert selected["review_subject_ids"] == [subject_id]
        with pytest.raises(ValueError, match="Reviewer"):
            workflow._find_assignable_reviewer(str(created[1]["_id"]))
        assert find_user_record(database, created[0]["_id"], active_only=True)
        assert {user["_id"] for user in users_by_ids(
            database, [created[0]["_id"], created[1]["_id"]], active_only=True,
        )} == {created[0]["_id"], created[1]["_id"]}
        assert {user["_id"] for user in review_candidate_users(database)} == {
            user["_id"] for user in created
        }
        assert active_admin_ids(database) == [created[2]["_id"]]
    finally:
        with postgres_connection() as conn:
            conn.execute("DELETE FROM users WHERE id=ANY(%s)",
                         ([str(user["_id"]) for user in created],))
