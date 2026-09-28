"""Write canonical audit events in the caller's PostgreSQL transaction."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from bson import ObjectId
from psycopg.types.json import Jsonb

from core.audit import build_audit_event


def _json(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    return value


def write_postgres_audit_event(
    conn, *, action: str, entity_type: str, entity_id,
    actor_user_id=None, actor_role: str | None = None,
    before: dict | None = None, after: dict | None = None,
    metadata: dict | None = None,
    service_name: str | None = None,
    **fields,
) -> None:
    event = build_audit_event(
        action=action, entity_type=entity_type, entity_id=entity_id,
        actor_user_id=actor_user_id, actor_role=actor_role,
        service_name=service_name,
        before=_json(before or {}), after=_json(after or {}),
        metadata=_json(metadata or {}), **fields,
    )
    payload = _json(event)
    actor = payload["actor"]
    entity = payload["entity"]
    conn.execute(
        """INSERT INTO audit_logs
           (id, actor_user_id, actor_type, actor_role, action, entity_type,
            entity_id, before_state, after_state, changes, before_hash,
            after_hash, metadata, payload, created_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (str(ObjectId()), actor["user_id"], actor["type"], actor["role"],
         payload["action"], entity["type"], entity["id"],
         Jsonb(payload["before"]), Jsonb(payload["after"]),
         Jsonb(payload["changes"]), payload["before_hash"],
         payload["after_hash"], Jsonb(payload["metadata"]), Jsonb(payload),
         event["created_at"]),
    )
