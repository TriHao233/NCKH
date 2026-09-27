"""Run with RUN_POSTGRES_INTEGRATION=1 and POSTGRES_DSN against a test database."""

import os
import uuid

import pytest

from core.config import settings
from core.postgres import postgres_connection
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
        updated = users.update(created["_id"], {"role": "Reviewer", "is_active": False})
        assert updated["role"] == "Reviewer"
        assert updated["is_active"] is False
        synced = users.sync_identity({"uid": uid, "email": email, "name": "New name"})
        assert synced["_id"] == created["_id"]
        assert synced["role"] == "Reviewer"
        assert synced["is_active"] is False
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
