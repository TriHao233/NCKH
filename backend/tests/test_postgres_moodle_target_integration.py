"""Run with RUN_POSTGRES_INTEGRATION=1 and POSTGRES_DSN on a test database."""

import os
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from bson import ObjectId

from core.config import settings
from core.postgres import postgres_connection
from db.copy_business_data import projected_rows, upsert
from modules.admin import moodle_service
from modules.admin.moodle_schemas import MoodleTargetPayload
from modules.admin.overview_service import AdminOverviewService
from modules.admin import postgres_moodle_target_repository
from modules.admin.postgres_moodle_target_repository import PostgresMoodleTargetRepository
from modules.users.postgres_repository import PostgresUserRepository


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1" or not settings.postgres_dsn,
    reason="Requires an explicitly configured PostgreSQL test database",
)


def test_moodle_target_lifecycle_is_postgres_backed(monkeypatch):
    monkeypatch.setattr(settings, "moodle_target_store", "postgres")
    monkeypatch.setattr(settings, "user_store", "postgres")
    monkeypatch.setattr(moodle_service, "record_audit_event",
                        lambda **fields: pytest.fail("MongoDB audit was called"))
    site_key = f"pg-{uuid4().hex[:12]}"
    user = PostgresUserRepository().create({
        "firebase_uid": site_key, "email": f"{site_key}@example.test",
        "display_name": "Admin", "role": "Admin",
    })
    actor = SimpleNamespace(id=user["_id"], role="Admin")
    service = moodle_service.MoodleTargetService(SimpleNamespace())
    payload = MoodleTargetPayload(
        site_key=site_key, site_name="Moodle thử nghiệm", mode="MOCK",
        default_course_id="course-1", default_category_id="category-1",
    )
    try:
        saved = service.save_target(payload, actor)
        assert saved["site_key"] == site_key
        assert saved["is_active"] is True
        assert saved["token_env_var"] == ""
        target_id = saved["_id"]
        assert service.find_target(site_key)["_id"] == ObjectId(target_id)
        assert service.find_target(target_id)["site_key"] == site_key
        assert [item["site_key"] for item in service.list_targets(include_inactive=False)["items"]]
        assert PostgresMoodleTargetRepository().count(active_only=True) >= 1
        assert AdminOverviewService(SimpleNamespace())._moodle_target_count(active_only=True) >= 1

        checked = service.check_target(site_key, actor)
        assert checked["check"]["ok"] is True
        assert checked["target"]["last_check"]["ok"] is True

        renamed = service.save_target(payload.model_copy(update={"site_name": "Tên mới"}), actor)
        assert renamed["_id"] == target_id
        assert renamed["site_name"] == "Tên mới"
        assert renamed["last_check"]["ok"] is True

        inactive = service.deactivate_target(target_id, actor)
        assert inactive["is_active"] is False
        assert service.find_target(site_key, active_only=True) is None
        assert all(item["site_key"] != site_key
                   for item in service.list_targets(include_inactive=False)["items"])
        with postgres_connection() as conn:
            audit = conn.execute(
                """SELECT action, actor_user_id, actor_role, entity_id, payload
                   FROM audit_logs WHERE entity_id=%s ORDER BY created_at, id""",
                (str(target_id),),
            ).fetchall()
        assert {row["action"] for row in audit} == {
            "admin.moodle_target_save", "admin.moodle_target_check",
            "admin.moodle_target_deactivate",
        }
        assert len(audit) == 4
        assert all(row["actor_user_id"] == str(actor.id) and row["actor_role"] == "Admin"
                   for row in audit)
        assert all(row["payload"]["entity"]["id"] == str(target_id) for row in audit)
    finally:
        with postgres_connection() as conn:
            conn.execute("DELETE FROM audit_logs WHERE entity_id IN "
                         "(SELECT id FROM moodle_targets WHERE site_key=%s)", (site_key,))
            conn.execute("DELETE FROM moodle_targets WHERE site_key=%s", (site_key,))
            conn.execute("DELETE FROM users WHERE id=%s", (str(user["_id"]),))


def test_shadow_copied_moodle_target_can_be_used_by_service(monkeypatch):
    monkeypatch.setattr(settings, "moodle_target_store", "postgres")
    monkeypatch.setattr(settings, "user_store", "postgres")
    site_key = f"copied-{uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    legacy = {
        "_id": ObjectId(), "site_key": site_key, "site_name": "Imported",
        "mode": "MOCK", "token_env_var": "MOODLE_TOKEN_ENV",
        "base_url": "", "default_course_id": "legacy-course",
        "default_category_id": "legacy-category", "allowed_roles": ["Reviewer"],
        "is_active": True, "created_at": now, "updated_at": now,
    }
    try:
        with postgres_connection() as conn:
            for table, row in projected_rows("moodle_targets", legacy):
                upsert(conn, table, row)
        target = moodle_service.MoodleTargetService(SimpleNamespace()).find_target(site_key)
        assert target["_id"] == legacy["_id"]
        assert target["token_env_var"] == "MOODLE_TOKEN_ENV"
        assert target["default_course_id"] == "legacy-course"
        assert target["allowed_roles"] == ["Reviewer"]
    finally:
        with postgres_connection() as conn:
            conn.execute("DELETE FROM moodle_targets WHERE site_key=%s", (site_key,))


def test_moodle_target_save_rolls_back_when_audit_fails(monkeypatch):
    monkeypatch.setattr(settings, "moodle_target_store", "postgres")
    monkeypatch.setattr(settings, "user_store", "postgres")
    site_key = f"rollback-{uuid4().hex[:12]}"

    def reject_audit(*_args, **_kwargs):
        raise RuntimeError("audit failed")

    monkeypatch.setattr(postgres_moodle_target_repository,
                        "write_postgres_audit_event", reject_audit)
    payload = MoodleTargetPayload(
        site_key=site_key, site_name="Rollback", mode="MOCK",
        default_course_id="course", default_category_id="category",
    )
    with pytest.raises(RuntimeError, match="audit failed"):
        moodle_service.MoodleTargetService(SimpleNamespace()).save_target(
            payload, SimpleNamespace(id=ObjectId(), role="Admin"),
        )
    with postgres_connection() as conn:
        assert conn.execute("SELECT id FROM moodle_targets WHERE site_key=%s",
                            (site_key,)).fetchone() is None


def test_moodle_target_postgres_requires_postgres_users(monkeypatch):
    monkeypatch.setattr(settings, "user_store", "mongo")
    with pytest.raises(RuntimeError, match="requires USER_STORE=postgres"):
        PostgresMoodleTargetRepository()
