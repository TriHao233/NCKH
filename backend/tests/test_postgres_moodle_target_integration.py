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
from modules.admin.postgres_moodle_target_repository import PostgresMoodleTargetRepository


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1" or not settings.postgres_dsn,
    reason="Requires an explicitly configured PostgreSQL test database",
)


def test_moodle_target_lifecycle_is_postgres_backed(monkeypatch):
    monkeypatch.setattr(settings, "moodle_target_store", "postgres")
    monkeypatch.setattr(moodle_service, "record_audit_event", lambda **fields: None)
    site_key = f"pg-{uuid4().hex[:12]}"
    actor = SimpleNamespace(id=ObjectId(), role="Admin")
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
    finally:
        with postgres_connection() as conn:
            conn.execute("DELETE FROM moodle_targets WHERE site_key=%s", (site_key,))


def test_shadow_copied_moodle_target_can_be_used_by_service(monkeypatch):
    monkeypatch.setattr(settings, "moodle_target_store", "postgres")
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
