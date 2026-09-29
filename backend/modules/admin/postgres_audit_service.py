"""Administrative audit pagination from the PostgreSQL business log."""

from __future__ import annotations

from datetime import datetime

from bson import ObjectId

from core.postgres import postgres_connection
from modules.admin.audit_service import _normalize_audit_log


class PostgresAuditService:
    def list(self, *, page: int, page_size: int,
             actor_user_id: str | None = None, entity_type: str | None = None,
             entity_id: str | None = None, action: str | None = None,
             date_from: datetime | None = None, date_to: datetime | None = None,
             search: str | None = None) -> dict:
        filters = ["true"]
        params = []
        if actor_user_id:
            filters.append("actor_user_id=%s")
            params.append(actor_user_id)
        if entity_type:
            filters.append("lower(entity_type)=lower(%s)")
            params.append(entity_type)
        if entity_id:
            filters.append("entity_id=%s")
            params.append(entity_id)
        if action:
            filters.append("action=%s")
            params.append(action)
        if date_from:
            filters.append("created_at >= %s")
            params.append(date_from)
        if date_to:
            filters.append("created_at <= %s")
            params.append(date_to)
        if search:
            filters.append("(action ILIKE %s OR actor_role ILIKE %s OR "
                           "entity_type ILIKE %s OR entity_id ILIKE %s OR "
                           "metadata->>'reason' ILIKE %s)")
            pattern = f"%{search}%"
            params.extend([pattern] * 5)
        where = " AND ".join(filters)
        with postgres_connection() as conn:
            total = conn.execute("SELECT count(*) AS n FROM audit_logs WHERE " + where,
                                 params).fetchone()["n"]
            rows = conn.execute(
                "SELECT * FROM audit_logs WHERE " + where
                + " ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s",
                [*params, page_size, (page - 1) * page_size],
            ).fetchall()
            user_ids = [row["actor_user_id"] for row in rows if row["actor_user_id"]]
            users = {}
            if user_ids:
                users = {
                    row["id"]: row["display_name"] or row["id"]
                    for row in conn.execute(
                        "SELECT id, display_name FROM users WHERE id=ANY(%s)",
                        (user_ids,),
                    ).fetchall()
                }
        items = []
        for row in rows:
            record = dict(row["payload"] or {})
            record.update({
                "_id": ObjectId(row["id"]), "action": row["action"],
                "actor_user_id": row["actor_user_id"],
                "actor_role": row["actor_role"],
                "entity_type": row["entity_type"], "entity_id": row["entity_id"],
                "before": row["before_state"], "after": row["after_state"],
                "changes": row["changes"], "metadata": row["metadata"],
                "before_hash": row["before_hash"], "after_hash": row["after_hash"],
                "created_at": row["created_at"],
            })
            item = _normalize_audit_log(record)
            actor_id = item["actor"]["user_id"]
            if actor_id in users:
                item["actor"]["user_name"] = users[actor_id]
            items.append(item)
        return {"items": items, "total": total, "page": page, "page_size": page_size}
