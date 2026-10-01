"""Run with RUN_POSTGRES_INTEGRATION=1 and POSTGRES_DSN against a test database."""

import os
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from bson import ObjectId
from psycopg.types.json import Jsonb

from core.config import settings
from core.postgres import postgres_connection
from modules.notifications.service import NotificationService
from modules.users.postgres_repository import PostgresUserRepository


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1" or not settings.postgres_dsn,
    reason="Requires an explicitly configured PostgreSQL test database",
)


def test_notification_inbox_is_owned_paginated_and_readable(monkeypatch):
    monkeypatch.setattr(settings, "user_store", "postgres")
    monkeypatch.setattr(settings, "notification_store", "postgres")
    suffix = uuid4().hex[:10]
    users = []
    try:
        for role in ("Teacher", "Reviewer"):
            users.append(PostgresUserRepository().create({
                "firebase_uid": f"notification-{role.lower()}-{suffix}",
                "email": f"notification-{role.lower()}-{suffix}@example.test",
                "display_name": role, "role": role,
            }))
        teacher = SimpleNamespace(id=users[0]["_id"])
        reviewer = SimpleNamespace(id=users[1]["_id"])
        service = NotificationService(SimpleNamespace())
        first = service.create(recipient_user_id=teacher.id, type="QUESTION_APPROVED",
                               title="Đã duyệt", actor_user_id=reviewer.id)
        second = service.create(recipient_user_id=teacher.id, type="QUESTION_NEEDS_REVISION",
                                title="Cần sửa", actor_user_id=reviewer.id)
        foreign = service.create(recipient_user_id=reviewer.id, type="QUESTION_REVIEW_ASSIGNED",
                                 title="Được phân công", actor_user_id=teacher.id)
        assert service.list(teacher, 1, 1)["total"] == 2
        assert len(service.list(teacher, 1, 1)["items"]) == 1
        assert service.unread_count(teacher) == 2
        assert service.mark_read(foreign["id"], teacher) is None
        assert service.mark_read(first["id"], teacher)["is_read"] is True
        assert service.mark_read(first["id"], teacher)["is_read"] is True
        assert service.unread_count(teacher) == 1
        assert service.list(teacher, 1, 10, unread_only=True)["items"][0]["id"] == second["id"]
        assert service.mark_all_read(teacher) == 1
        assert service.mark_all_read(teacher) == 0
        assert service.unread_count(teacher) == 0
        assert service.unread_count(reviewer) == 1

        # Historical Mongo records may have is_read=true without a read_at.
        legacy_id = str(ObjectId())
        with postgres_connection() as conn:
            conn.execute("""
                INSERT INTO notifications
                    (id, recipient_user_id, kind, payload, read_at, created_at)
                VALUES (%s,%s,%s,%s,NULL,%s)
            """, (legacy_id, str(teacher.id), "LEGACY",
                  Jsonb({"type": "LEGACY", "title": "Đã đọc", "is_read": True}),
                  datetime.now(timezone.utc)))
        assert service.unread_count(teacher) == 0
        assert service.list(teacher, 1, 10)["total"] == 3
    finally:
        with postgres_connection() as conn:
            with conn.transaction():
                for user in users:
                    conn.execute("DELETE FROM notifications WHERE recipient_user_id=%s", (str(user["_id"]),))
                    conn.execute("DELETE FROM users WHERE id=%s", (str(user["_id"]),))
