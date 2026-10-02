"""PostgreSQL repository for internal contact / support tickets."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from bson import ObjectId
from psycopg.types.json import Jsonb

from core.postgres import postgres_connection


def _request_row(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "ticket_code": row["ticket_code"],
        "user_id": row["user_id"],
        "user_name": row.get("user_name") or "",
        "user_email": row.get("user_email") or "",
        "user_role": row.get("user_role") or "",
        "category": row["category"],
        "title": row["title"],
        "content": row["content"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "resolved_at": row["resolved_at"],
        "withdrawn_at": row.get("withdrawn_at"),
        "deleted_at": row.get("deleted_at"),
        "deleted_by": row.get("deleted_by"),
        "message_count": row.get("message_count") or 0,
    }


def _message_row(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "request_id": row["request_id"],
        "sender_id": row["sender_id"],
        "sender_name": row.get("sender_name") or "",
        "sender_role": row.get("sender_role") or "",
        "message": row["message"],
        "created_at": row["created_at"],
    }


class PostgresContactRepository:
    def create_request(self, record: dict) -> dict:
        with postgres_connection() as conn:
            row = conn.execute(
                """
                INSERT INTO contact_requests
                    (id, ticket_code, user_id, category, title, content,
                     status, created_at, updated_at, resolved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    record["id"], record["ticket_code"], record["user_id"],
                    record["category"], record["title"], record["content"],
                    record["status"], record["created_at"], record["updated_at"],
                    record.get("resolved_at"),
                ),
            ).fetchone()
        return _request_row(row)

    def find_request(self, request_id: str) -> dict | None:
        with postgres_connection() as conn:
            row = conn.execute(
                """
                SELECT r.*, u.display_name AS user_name, u.email AS user_email, u.role AS user_role,
                       (SELECT count(*) FROM contact_messages m WHERE m.request_id=r.id)
                           AS message_count
                FROM contact_requests r
                LEFT JOIN users u ON u.id = r.user_id
                WHERE r.id = %s
                """,
                (request_id,),
            ).fetchone()
        return _request_row(row)

    def list_requests(
        self,
        *,
        page: int,
        page_size: int,
        user_id: str | None = None,
        status: str | None = None,
        category: str | None = None,
        search: str | None = None,
        deleted: bool = False,
    ) -> tuple[list[dict], int]:
        clauses: list[str] = ["r.deleted_at IS NOT NULL" if deleted else "r.deleted_at IS NULL"]
        params: list[Any] = []
        if user_id:
            clauses.append("r.user_id = %s")
            params.append(user_id)
        if status:
            clauses.append("r.status = %s")
            params.append(status)
        if category:
            clauses.append("r.category = %s")
            params.append(category)
        if search:
            clauses.append("(r.title ILIKE %s OR r.ticket_code ILIKE %s OR r.content ILIKE %s)")
            like = f"%{search}%"
            params.extend([like, like, like])
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with postgres_connection() as conn:
            total = conn.execute(
                f"SELECT count(*) AS n FROM contact_requests r{where}",
                params,
            ).fetchone()["n"]
            rows = conn.execute(
                f"""
                SELECT r.*, u.display_name AS user_name, u.email AS user_email, u.role AS user_role,
                       (SELECT count(*) FROM contact_messages m WHERE m.request_id=r.id)
                           AS message_count
                FROM contact_requests r
                LEFT JOIN users u ON u.id = r.user_id
                {where}
                ORDER BY r.updated_at DESC, r.id DESC
                LIMIT %s OFFSET %s
                """,
                [*params, page_size, (page - 1) * page_size],
            ).fetchall()
        return [_request_row(row) for row in rows], total

    def update_status(
        self, request_id: str, status: str, now: datetime,
        *, resolved_at: datetime | None = None,
    ) -> dict | None:
        with postgres_connection() as conn:
            row = conn.execute(
                """
                UPDATE contact_requests
                SET status = %s,
                    updated_at = %s,
                    resolved_at = CASE
                        WHEN %s IN ('RESOLVED', 'CLOSED') THEN COALESCE(resolved_at, %s)
                        ELSE resolved_at
                    END
                WHERE id = %s AND deleted_at IS NULL AND status <> 'WITHDRAWN'
                RETURNING *
                """,
                (status, now, status, resolved_at or now, request_id),
            ).fetchone()
        return _request_row(row)

    def submit_response(
        self, request: dict, actor_id: str, status: str,
        message: str | None, now: datetime,
    ) -> dict | None:
        """Commit the selected status and optional message as one action."""
        with postgres_connection() as conn:
            row = conn.execute(
                """UPDATE contact_requests
                   SET status = %s, updated_at = %s,
                       resolved_at = CASE
                           WHEN %s IN ('RESOLVED', 'CLOSED') THEN COALESCE(resolved_at, %s)
                           ELSE resolved_at
                       END
                   WHERE id = %s AND updated_at = %s AND deleted_at IS NULL
                     AND status NOT IN ('WITHDRAWN', 'CLOSED')
                   RETURNING *""",
                (status, now, status, now, request["id"], request["updated_at"]),
            ).fetchone()
            if not row:
                return None
            if message:
                conn.execute(
                    """INSERT INTO contact_messages
                       (id, request_id, sender_id, message, created_at)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (str(ObjectId()), request["id"], actor_id, message, now),
                )
        return _request_row(row)

    @staticmethod
    def _record_event(conn, request_id: str, actor_id: str, action: str,
                      old_value: dict, new_value: dict, now: datetime) -> None:
        from bson import ObjectId

        conn.execute(
            """INSERT INTO contact_request_events
               (id, request_id, actor_id, action, old_value, new_value, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (str(ObjectId()), request_id, actor_id, action,
             Jsonb(old_value), Jsonb(new_value), now),
        )

    def edit_request(self, request: dict, changes: dict, actor_id: str,
                     now: datetime, *, admin_reclassify: bool = False) -> dict | None:
        old_value = {key: request[key] for key in changes}
        with postgres_connection() as conn:
            if admin_reclassify:
                row = conn.execute(
                    """UPDATE contact_requests
                       SET category = %s, updated_at = %s
                       WHERE id = %s AND updated_at = %s AND deleted_at IS NULL
                         AND status <> 'WITHDRAWN' RETURNING *""",
                    (changes["category"], now, request["id"], request["updated_at"]),
                ).fetchone()
            else:
                row = conn.execute(
                    """UPDATE contact_requests
                       SET category = %s, title = %s, content = %s, updated_at = %s
                       WHERE id = %s AND updated_at = %s AND status = 'NEW'
                         AND deleted_at IS NULL
                         AND NOT EXISTS (SELECT 1 FROM contact_messages WHERE request_id = %s)
                       RETURNING *""",
                    (changes.get("category", request["category"]),
                     changes.get("title", request["title"]),
                     changes.get("content", request["content"]), now,
                     request["id"], request["updated_at"], request["id"]),
                ).fetchone()
            if row:
                self._record_event(conn, request["id"], actor_id,
                                   "RECLASSIFIED" if admin_reclassify else "EDITED",
                                   old_value, changes, now)
        return _request_row(row)

    def withdraw_request(self, request: dict, actor_id: str, now: datetime) -> dict | None:
        with postgres_connection() as conn:
            row = conn.execute(
                """UPDATE contact_requests
                   SET status = 'WITHDRAWN', withdrawn_at = %s, updated_at = %s
                   WHERE id = %s AND updated_at = %s AND deleted_at IS NULL
                     AND status IN ('NEW', 'IN_PROGRESS') RETURNING *""",
                (now, now, request["id"], request["updated_at"]),
            ).fetchone()
            if row:
                self._record_event(conn, request["id"], actor_id, "WITHDRAWN",
                                   {"status": request["status"]}, {"status": "WITHDRAWN"}, now)
        return _request_row(row)

    def delete_request(self, request: dict, actor_id: str, now: datetime,
                       *, allow_new: bool) -> dict | None:
        with postgres_connection() as conn:
            row = conn.execute(
                """UPDATE contact_requests
                   SET deleted_at = %s, deleted_by = %s, updated_at = %s
                   WHERE id = %s AND updated_at = %s AND deleted_at IS NULL
                     AND (status IN ('WITHDRAWN', 'RESOLVED', 'CLOSED')
                       OR (%s AND status = 'NEW' AND NOT EXISTS
                           (SELECT 1 FROM contact_messages WHERE request_id = %s)))
                   RETURNING *""",
                (now, actor_id, now, request["id"], request["updated_at"],
                 allow_new, request["id"]),
            ).fetchone()
            if row:
                self._record_event(conn, request["id"], actor_id, "DELETED",
                                   {}, {"deleted": True}, now)
        return _request_row(row)

    def restore_request(self, request: dict, actor_id: str, now: datetime) -> dict | None:
        with postgres_connection() as conn:
            row = conn.execute(
                """UPDATE contact_requests
                   SET deleted_at = NULL, deleted_by = NULL, updated_at = %s
                   WHERE id = %s AND updated_at = %s AND deleted_at IS NOT NULL
                   RETURNING *""",
                (now, request["id"], request["updated_at"]),
            ).fetchone()
            if row:
                self._record_event(conn, request["id"], actor_id, "RESTORED",
                                   {"deleted": True}, {"deleted": False}, now)
        return _request_row(row)

    def list_events(self, request_id: str) -> list[dict]:
        with postgres_connection() as conn:
            rows = conn.execute(
                """SELECT e.*, u.display_name AS actor_name
                   FROM contact_request_events e
                   LEFT JOIN users u ON u.id = e.actor_id
                   WHERE e.request_id = %s
                   ORDER BY e.created_at ASC, e.id ASC""",
                (request_id,),
            ).fetchall()
        return [{"id": row["id"], "actor_name": row.get("actor_name") or "",
                 "action": row["action"], "old_value": row["old_value"],
                 "new_value": row["new_value"], "created_at": row["created_at"]}
                for row in rows]

    def touch(self, request_id: str, now: datetime) -> None:
        with postgres_connection() as conn:
            conn.execute(
                "UPDATE contact_requests SET updated_at = %s WHERE id = %s",
                (now, request_id),
            )

    def add_message(self, record: dict) -> dict:
        with postgres_connection() as conn:
            row = conn.execute(
                """
                INSERT INTO contact_messages
                    (id, request_id, sender_id, message, created_at)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    record["id"], record["request_id"], record["sender_id"],
                    record["message"], record["created_at"],
                ),
            ).fetchone()
            enriched = conn.execute(
                """
                SELECT m.*, u.display_name AS sender_name, u.role AS sender_role
                FROM contact_messages m
                LEFT JOIN users u ON u.id = m.sender_id
                WHERE m.id = %s
                """,
                (row["id"],),
            ).fetchone()
        return _message_row(enriched)

    def list_messages(self, request_id: str) -> list[dict]:
        with postgres_connection() as conn:
            rows = conn.execute(
                """
                SELECT m.*, u.display_name AS sender_name, u.role AS sender_role
                FROM contact_messages m
                LEFT JOIN users u ON u.id = m.sender_id
                WHERE m.request_id = %s
                ORDER BY m.created_at ASC, m.id ASC
                """,
                (request_id,),
            ).fetchall()
        return [_message_row(row) for row in rows]

    def next_ticket_sequence(self, year: int) -> int:
        prefix = f"CT-{year}-"
        with postgres_connection() as conn:
            row = conn.execute(
                """
                SELECT ticket_code FROM contact_requests
                WHERE ticket_code LIKE %s
                ORDER BY ticket_code DESC LIMIT 1
                """,
                (prefix + "%",),
            ).fetchone()
        if not row:
            return 1
        try:
            last = int(row["ticket_code"].rsplit("-", 1)[-1])
        except (ValueError, KeyError):
            return 1
        return last + 1
