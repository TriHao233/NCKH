"""PostgreSQL notification inbox with the same API shape as the Mongo store."""

from __future__ import annotations

from datetime import datetime

from bson import ObjectId
from psycopg.types.json import Jsonb

from core.config import settings
from core.postgres import postgres_connection

UNREAD = "read_at IS NULL AND NOT (payload @> '{\"is_read\": true}'::jsonb)"


def _json(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    return value


def _record(row: dict | None) -> dict | None:
    if row is None:
        return None
    record = dict(row["payload"] or {})
    record.update({
        "_id": ObjectId(row["id"]),
        "recipient_user_id": ObjectId(row["recipient_user_id"]),
        "type": row["kind"],
        "read_at": row["read_at"],
        "is_read": bool(row["read_at"] or record.get("is_read")),
        "created_at": row["created_at"],
    })
    return record


class PostgresNotificationRepository:
    def __init__(self) -> None:
        if settings.user_store != "postgres":
            raise RuntimeError("NOTIFICATION_STORE=postgres requires USER_STORE=postgres")

    def create(self, record: dict) -> dict:
        with postgres_connection() as conn:
            row = conn.execute("""
                INSERT INTO notifications
                    (id, recipient_user_id, kind, payload, read_at, created_at)
                VALUES (%s,%s,%s,%s,%s,%s) RETURNING *
            """, (str(record["_id"]), str(record["recipient_user_id"]), record["type"],
                  Jsonb(_json(record)), record["read_at"], record["created_at"])).fetchone()
        return _record(row)

    def list(self, recipient_user_id: ObjectId, page: int, page_size: int,
             *, unread_only: bool = False) -> tuple[list[dict], int]:
        condition = "recipient_user_id=%s" + (f" AND {UNREAD}" if unread_only else "")
        with postgres_connection() as conn:
            total = conn.execute(
                f"SELECT count(*) AS n FROM notifications WHERE {condition}",
                (str(recipient_user_id),),
            ).fetchone()["n"]
            rows = conn.execute(f"""
                SELECT * FROM notifications WHERE {condition}
                ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s
            """, (str(recipient_user_id), page_size, (page - 1) * page_size)).fetchall()
        return [_record(row) for row in rows], total

    def unread_count(self, recipient_user_id: ObjectId) -> int:
        with postgres_connection() as conn:
            return conn.execute(f"""
                SELECT count(*) AS n FROM notifications
                WHERE recipient_user_id=%s AND {UNREAD}
            """, (str(recipient_user_id),)).fetchone()["n"]

    def mark_read(self, notification_id: ObjectId, recipient_user_id: ObjectId,
                  now: datetime) -> dict | None:
        with postgres_connection() as conn:
            row = conn.execute("""
                UPDATE notifications SET
                    read_at=COALESCE(read_at, %s),
                    payload=jsonb_set(payload, '{is_read}', 'true'::jsonb, true)
                WHERE id=%s AND recipient_user_id=%s RETURNING *
            """, (now, str(notification_id), str(recipient_user_id))).fetchone()
        return _record(row)

    def mark_all_read(self, recipient_user_id: ObjectId, now: datetime) -> int:
        with postgres_connection() as conn:
            result = conn.execute(f"""
                UPDATE notifications SET read_at=%s,
                    payload=jsonb_set(payload, '{{is_read}}', 'true'::jsonb, true)
                WHERE recipient_user_id=%s AND {UNREAD}
            """, (now, str(recipient_user_id)))
            return result.rowcount
