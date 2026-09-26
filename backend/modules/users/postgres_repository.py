"""PostgreSQL implementation of the existing user repository contract."""

from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId
from psycopg import sql
from psycopg.types.json import Jsonb

from core.postgres import postgres_connection

JSON_FIELDS = {"permissions", "profile", "generation_presets", "task_calendar"}
UPDATE_FIELDS = JSON_FIELDS | {"email", "display_name", "role", "is_active"}
TASK_DATES = {"created_at", "updated_at", "completed_at", "due_date", "createdAt", "updatedAt"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _id(value: str | ObjectId) -> str:
    try:
        return str(ObjectId(value))
    except Exception as exc:
        raise ValueError("ID người dùng không hợp lệ") from exc


def _json_value(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def _task_dates(value):
    if isinstance(value, list):
        return [_task_dates(item) for item in value]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in TASK_DATES and isinstance(item, str):
                try:
                    result[key] = datetime.fromisoformat(item.replace("Z", "+00:00"))
                    continue
                except ValueError:
                    pass
            result[key] = _task_dates(item)
        return result
    return value


def _user(row: dict | None) -> dict | None:
    if row is None:
        return None
    result = dict(row)
    result["_id"] = ObjectId(result.pop("id"))
    result["task_calendar"] = _task_dates(result.get("task_calendar") or [])
    result["generation_presets"] = _task_dates(result.get("generation_presets") or [])
    return result


def _business_record(row: dict) -> dict:
    data = dict(row["payload"])
    data["_id"] = ObjectId(row["id"])
    data["created_at"] = row["created_at"]
    data["updated_at"] = row["updated_at"]
    return data


class PostgresUserRepository:
    def find_by_id(self, user_id: str | ObjectId) -> dict | None:
        with postgres_connection() as conn:
            return _user(conn.execute("SELECT * FROM users WHERE id = %s", (_id(user_id),)).fetchone())

    def find_by_firebase_uid(self, firebase_uid: str) -> dict | None:
        with postgres_connection() as conn:
            return _user(conn.execute(
                "SELECT * FROM users WHERE firebase_uid = %s", (firebase_uid,)
            ).fetchone())

    def find_by_email(self, email: str) -> dict | None:
        with postgres_connection() as conn:
            return _user(conn.execute(
                "SELECT * FROM users WHERE lower(email) = lower(%s)", (email,)
            ).fetchone())

    def create(self, data: dict) -> dict:
        now = _utc_now()
        user_id = str(ObjectId())
        with postgres_connection() as conn:
            row = conn.execute(
                """INSERT INTO users (
                    id, firebase_uid, email, display_name, role, permissions, profile,
                    generation_presets, task_calendar, is_active, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, '[]'::jsonb, '[]'::jsonb, true, %s, %s)
                RETURNING *""",
                (
                    user_id, data["firebase_uid"], data["email"].lower(),
                    data["display_name"], data.get("role", "Teacher"),
                    Jsonb(_json_value(data.get("permissions") or [])),
                    Jsonb(_json_value(data.get("profile") or {})), now, now,
                ),
            ).fetchone()
        return _user(row)

    def sync_identity(self, claims: dict) -> dict:
        firebase_uid = claims["uid"]
        email = (claims.get("email") or f"{firebase_uid}@firebase.local").lower()
        display_name = claims.get("name") or email.split("@", 1)[0]
        avatar = claims.get("picture") or ""
        now = _utc_now()
        with postgres_connection() as conn:
            # Preserve the old profile/role when Firebase refreshes its claims.
            existing = conn.execute(
                """SELECT * FROM users
                   WHERE firebase_uid = %s OR lower(email) = lower(%s)
                   ORDER BY (firebase_uid = %s) DESC LIMIT 1 FOR UPDATE""",
                (firebase_uid, email, firebase_uid),
            ).fetchone()
            if existing:
                profile = {"school": "", "address": "", "avatar": "", **(existing["profile"] or {})}
                if avatar:
                    profile["avatar"] = avatar
                row = conn.execute(
                    """UPDATE users SET firebase_uid = %s, email = %s, profile = %s,
                       updated_at = %s WHERE id = %s RETURNING *""",
                    (firebase_uid, email, Jsonb(profile), now, existing["id"]),
                ).fetchone()
            else:
                row = conn.execute(
                    """INSERT INTO users (
                        id, firebase_uid, email, display_name, role, permissions, profile,
                        generation_presets, task_calendar, is_active, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, 'Teacher', '[]'::jsonb, %s,
                              '[]'::jsonb, '[]'::jsonb, true, %s, %s)
                    RETURNING *""",
                    (
                        str(ObjectId()), firebase_uid, email, display_name,
                        Jsonb({"school": "", "address": "", "avatar": avatar}), now, now,
                    ),
                ).fetchone()
        return _user(row)

    def list(self, page: int, page_size: int, role: str | None, search: str | None):
        conditions = []
        params = []
        if role:
            conditions.append("role = %s")
            params.append(role)
        if search:
            conditions.append("(display_name ILIKE %s OR email ILIKE %s)")
            params.extend([f"%{search}%", f"%{search}%"])
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        with postgres_connection() as conn:
            total = conn.execute("SELECT count(*) AS n FROM users" + where, params).fetchone()["n"]
            rows = conn.execute(
                "SELECT * FROM users" + where + " ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s",
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return [_user(row) for row in rows], total

    def update(self, user_id: str | ObjectId, fields: dict) -> dict | None:
        unknown = set(fields) - UPDATE_FIELDS
        if unknown:
            raise ValueError(f"Unsupported user update fields: {', '.join(sorted(unknown))}")
        changes = {**fields, "updated_at": _utc_now()}
        assignments = sql.SQL(", ").join(
            sql.SQL("{} = %s").format(sql.Identifier(key)) for key in changes
        )
        values = [Jsonb(_json_value(value)) if key in JSON_FIELDS else value
                  for key, value in changes.items()]
        with postgres_connection() as conn:
            row = conn.execute(
                sql.SQL("UPDATE users SET {} WHERE id = %s RETURNING *").format(assignments),
                (*values, _id(user_id)),
            ).fetchone()
        return _user(row)

    def count_active_admins(self) -> int:
        with postgres_connection() as conn:
            return conn.execute(
                "SELECT count(*) AS n FROM users WHERE role = 'Admin' AND is_active"
            ).fetchone()["n"]

    def delete_by_id(self, user_id: str | ObjectId) -> None:
        with postgres_connection() as conn:
            conn.execute("DELETE FROM users WHERE id = %s", (_id(user_id),))

    def get_stats(self, user_id: str | ObjectId) -> dict:
        uid = _id(user_id)
        with postgres_connection() as conn:
            row = conn.execute(
                """SELECT
                   (SELECT count(*) FROM documents WHERE uploaded_by_user_id = %s AND status <> 'ARCHIVED') AS documents_count,
                   (SELECT count(*) FROM questions WHERE created_by_user_id = %s AND lifecycle_status <> 'ARCHIVED') AS questions_count,
                   (SELECT count(*) FROM questions WHERE created_by_user_id = %s AND review_status = 'PENDING') AS pending_questions_count""",
                (uid, uid, uid),
            ).fetchone()
        return dict(row)

    def get_calendar_documents(self, user_id: str | ObjectId) -> list[dict]:
        with postgres_connection() as conn:
            rows = conn.execute(
                "SELECT id, payload, created_at, updated_at FROM documents "
                "WHERE uploaded_by_user_id = %s AND status <> 'ARCHIVED'",
                (_id(user_id),),
            ).fetchall()
        return [_business_record(row) for row in rows]

    def get_calendar_questions(self, user_id: str | ObjectId) -> list[dict]:
        with postgres_connection() as conn:
            rows = conn.execute(
                "SELECT id, payload, created_at, updated_at FROM questions "
                "WHERE created_by_user_id = %s AND lifecycle_status <> 'ARCHIVED'",
                (_id(user_id),),
            ).fetchall()
        return [_business_record(row) for row in rows]

    def get_document_ids_with_questions(self, document_ids: list[ObjectId]) -> set[str]:
        if not document_ids:
            return set()
        with postgres_connection() as conn:
            rows = conn.execute(
                """SELECT DISTINCT payload ->> 'document_id' AS document_id FROM questions
                   WHERE payload ->> 'document_id' = ANY(%s) AND lifecycle_status <> 'ARCHIVED'""",
                ([str(item) for item in document_ids],),
            ).fetchall()
        return {row["document_id"] for row in rows if row["document_id"]}
