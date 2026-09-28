"""PostgreSQL source for Moodle target configuration (not publications)."""

from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId
from psycopg.types.json import Jsonb

from core.bootstrap import SCHEMA_VERSION
from core.postgres import postgres_connection


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json(item) for item in value]
    return value


def _target(row: dict | None) -> dict | None:
    if row is None:
        return None
    record = dict(row["payload"] or {})
    record.update({
        "_id": ObjectId(row["id"]), "site_key": row["site_key"],
        "site_name": row["site_name"], "mode": row["mode"],
        "token_env_var": row["secret_ref"] or "", "is_active": row["is_active"],
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    })
    return record


class PostgresMoodleTargetRepository:
    def list(self, *, include_inactive: bool = True) -> list[dict]:
        with postgres_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM moodle_targets "
                + ("" if include_inactive else "WHERE is_active ")
                + "ORDER BY site_key"
            ).fetchall()
        return [_target(row) for row in rows]

    def find(self, identifier: str | ObjectId, *, active_only: bool = False) -> dict | None:
        key = str(identifier)
        with postgres_connection() as conn:
            row = conn.execute(
                "SELECT * FROM moodle_targets WHERE (site_key=%s OR id=%s) "
                + ("AND is_active " if active_only else "")
                + "ORDER BY CASE WHEN site_key=%s THEN 0 ELSE 1 END LIMIT 1",
                (key, key, key),
            ).fetchone()
        return _target(row)

    def save(self, data: dict, actor_user_id: ObjectId) -> dict:
        now = _now()
        payload = {
            "schema_version": SCHEMA_VERSION, **data,
            "created_by_user_id": str(actor_user_id),
            "updated_by_user_id": str(actor_user_id),
            "last_check": None,
        }
        with postgres_connection() as conn:
            row = conn.execute(
                """INSERT INTO moodle_targets
                   (id, site_key, site_name, mode, secret_ref, is_active,
                    payload, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (site_key) DO UPDATE SET
                       site_name=EXCLUDED.site_name, mode=EXCLUDED.mode,
                       secret_ref=EXCLUDED.secret_ref, is_active=EXCLUDED.is_active,
                       payload=moodle_targets.payload ||
                           (EXCLUDED.payload - 'created_by_user_id' - 'last_check'),
                       updated_at=EXCLUDED.updated_at
                   RETURNING *""",
                (str(ObjectId()), data["site_key"], data["site_name"], data["mode"],
                 data.get("token_env_var") or None, data.get("is_active", True),
                 Jsonb(_json(payload)), now, now),
            ).fetchone()
        return _target(row)

    def deactivate(self, identifier: str | ObjectId, actor_user_id: ObjectId) -> dict | None:
        target = self.find(identifier)
        if not target:
            return None
        with postgres_connection() as conn:
            row = conn.execute(
                """UPDATE moodle_targets SET is_active=false,
                       payload=payload || %s, updated_at=%s
                   WHERE id=%s RETURNING *""",
                (Jsonb({"is_active": False, "updated_by_user_id": str(actor_user_id)}),
                 _now(), str(target["_id"])),
            ).fetchone()
        return _target(row)

    def update_check(self, identifier: str | ObjectId, check: dict,
                     actor_user_id: ObjectId) -> dict | None:
        target = self.find(identifier)
        if not target:
            return None
        with postgres_connection() as conn:
            row = conn.execute(
                """UPDATE moodle_targets SET payload=payload || %s, updated_at=%s
                   WHERE id=%s RETURNING *""",
                (Jsonb(_json({"last_check": check, "updated_by_user_id": actor_user_id})),
                 _now(), str(target["_id"])),
            ).fetchone()
        return _target(row)

    def count(self, *, active_only: bool = False) -> int:
        with postgres_connection() as conn:
            return conn.execute(
                "SELECT count(*) AS n FROM moodle_targets"
                + (" WHERE is_active" if active_only else "")
            ).fetchone()["n"]
