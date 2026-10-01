"""Run with RUN_POSTGRES_INTEGRATION=1 and POSTGRES_DSN against a test database."""

import os
import uuid
from datetime import datetime, timezone

import pytest
from bson import ObjectId

from core.config import settings
from core.dependencies import effective_permissions
from core.postgres import postgres_connection
from db.copy_business_data import projected_rows, upsert
from modules.auth.postgres_session_repository import PostgresFirebaseSessionRepository
from modules.users.postgres_repository import PostgresUserRepository


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1" or not settings.postgres_dsn,
    reason="Requires an explicitly configured PostgreSQL test database",
)


def test_user_identity_role_and_session_storage():
    suffix = uuid.uuid4().hex[:12]
    uid = f"test-{suffix}"
    email = f"test-{suffix}@example.test"
    users = PostgresUserRepository()
    sessions = PostgresFirebaseSessionRepository()
    created = None
    try:
        created = users.create({
            "firebase_uid": uid, "email": email, "display_name": "Teacher Test",
            "role": "Teacher", "permissions": ["questions.create"],
        })
        assert users.find_by_email(email)["_id"] == created["_id"]
        review_subject_id = ObjectId()
        updated = users.update(created["_id"], {
            "role": "Reviewer", "is_active": False,
            "permission_revokes": ["reviews.manage"],
            "review_subject_ids": [review_subject_id],
        })
        assert updated["role"] == "Reviewer"
        assert updated["is_active"] is False
        assert updated["review_subject_ids"] == [review_subject_id]
        assert "reviews.manage" not in effective_permissions(updated)
        synced = users.sync_identity({"uid": uid, "email": email, "name": "New name"})
        assert synced["_id"] == created["_id"]
        assert synced["role"] == "Reviewer"
        assert synced["is_active"] is False
        assert synced["review_subject_ids"] == [review_subject_id]
        sessions.upsert(uid, "untrusted-bearer-token")
        stored = sessions.find_by_uid(uid)
        assert stored is None
        sessions.upsert(uid, None)
        stored = sessions.find_by_uid(uid)
        assert stored["demo_token_hash"] is None
        assert stored["revoked_at"] is not None
    finally:
        if created:
            with postgres_connection() as conn:
                conn.execute("DELETE FROM users WHERE id=%s", (str(created["_id"]),))


def test_shadow_copy_preserves_reviewer_overrides_and_subjects():
    now = datetime.now(timezone.utc)
    user_id, subject_id = ObjectId(), ObjectId()
    legacy = {
        "_id": user_id, "firebase_uid": f"copied-{user_id}",
        "email": f"copied-{user_id}@example.test", "display_name": "Reviewer",
        "role": "Reviewer", "permissions": [],
        "permission_grants": ["questions.manage_all"],
        "permission_revokes": ["reviews.manage"],
        "review_subject_ids": [subject_id],
        "created_at": now, "updated_at": now,
    }
    try:
        with postgres_connection() as conn:
            for table, row in projected_rows("users", legacy):
                upsert(conn, table, row)
        copied = PostgresUserRepository().find_by_id(user_id)
        assert copied["permission_grants"] == ["questions.manage_all"]
        assert copied["permission_revokes"] == ["reviews.manage"]
        assert copied["review_subject_ids"] == [subject_id]
        assert "reviews.manage" not in effective_permissions(copied)
    finally:
        with postgres_connection() as conn:
            conn.execute("DELETE FROM users WHERE id=%s", (str(user_id),))
