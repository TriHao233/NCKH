"""Run with RUN_POSTGRES_INTEGRATION=1 and POSTGRES_DSN on a test database."""

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from bson import ObjectId

from core.audit import build_audit_event
from core.config import settings
from core.postgres import postgres_connection
from core.postgres_audit import write_postgres_audit_event
from db.copy_business_data import projected_rows, upsert
from modules.users.postgres_repository import PostgresUserRepository


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1" or not settings.postgres_dsn,
    reason="Requires an explicitly configured PostgreSQL test database",
)


def test_canonical_and_legacy_audit_events_keep_actor_entity_and_payload():
    suffix = uuid4().hex[:12]
    user = PostgresUserRepository().create({
        "firebase_uid": f"audit-{suffix}", "email": f"audit-{suffix}@example.test",
        "display_name": "Reviewer", "role": "Reviewer",
    })
    question_id = ObjectId()
    canonical = build_audit_event(
        action="QUESTION_APPROVED", entity_type="QUESTION", entity_id=question_id,
        actor_user_id=user["_id"], actor_role="Reviewer",
        before={"status": "PENDING"}, after={"status": "APPROVED"},
        before_hash="old-hash", after_hash="new-hash",
        metadata={"reason": "checked"},
    )
    canonical["_id"] = ObjectId()
    legacy = {
        "_id": ObjectId(), "actor_user_id": user["_id"],
        "actor_role": "Reviewer", "entity_type": "question", "entity_id": question_id,
        "action": "QUESTION_REVIEWED", "before": {"status": "DRAFT"},
        "after": {"status": "PENDING"}, "created_at": datetime.now(timezone.utc),
    }
    native_action = f"test.audit.{suffix}"
    try:
        with postgres_connection() as conn:
            for event in (canonical, legacy):
                for table, row in projected_rows("audit_logs", event):
                    upsert(conn, table, row)
            write_postgres_audit_event(
                conn, action=native_action, entity_type="question", entity_id=question_id,
                actor_user_id=user["_id"], actor_role="Reviewer",
                before={"status": "PENDING"}, after={"status": "APPROVED"},
            )
            rows = conn.execute(
                """SELECT id, actor_user_id, actor_type, actor_role, entity_type,
                          entity_id, changes, before_hash, after_hash, payload
                   FROM audit_logs WHERE id=ANY(%s)""",
                ([str(canonical["_id"]), str(legacy["_id"])],),
            ).fetchall()
        by_id = {row["id"]: row for row in rows}
        current = by_id[str(canonical["_id"])]
        assert current["actor_user_id"] == str(user["_id"])
        assert current["actor_type"] == "USER"
        assert current["actor_role"] == "Reviewer"
        assert current["entity_type"] == "question"
        assert current["entity_id"] == str(question_id)
        assert current["changes"] == [{
            "path": "status", "old_value": "PENDING", "new_value": "APPROVED",
        }]
        assert current["before_hash"] == "old-hash"
        assert current["after_hash"] == "new-hash"
        assert current["payload"]["actor"]["user_id"] == str(user["_id"])
        assert current["payload"]["entity"]["id"] == str(question_id)
        older = by_id[str(legacy["_id"])]
        assert older["actor_user_id"] == str(user["_id"])
        assert older["entity_id"] == str(question_id)
        assert older["actor_role"] == "Reviewer"
        assert older["payload"]["before"] == {"status": "DRAFT"}
        with postgres_connection() as conn:
            native = conn.execute(
                "SELECT actor_role, entity_id, changes, payload FROM audit_logs WHERE action=%s",
                (native_action,),
            ).fetchone()
        assert native["actor_role"] == "Reviewer"
        assert native["entity_id"] == str(question_id)
        assert native["changes"] == [{
            "path": "status", "old_value": "PENDING", "new_value": "APPROVED",
        }]
        assert native["payload"]["actor"]["user_id"] == str(user["_id"])
    finally:
        with postgres_connection() as conn:
            conn.execute("DELETE FROM audit_logs WHERE id=ANY(%s)",
                         ([str(canonical["_id"]), str(legacy["_id"])],))
            conn.execute("DELETE FROM audit_logs WHERE action=%s", (native_action,))
            conn.execute("DELETE FROM users WHERE id=%s", (str(user["_id"]),))
