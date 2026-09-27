"""Single writer for audit_logs.

Every event is stored in one canonical shape:

    {
        "schema_version": 2,
        "action": "QUESTION_APPROVED",
        "actor": {"type": "USER" | "SYSTEM", "user_id", "role", "model_id", "service_name"},
        "entity": {"type": "question", "id", "version_id"},
        "changes": [{"path", "old_value", "new_value"}],
        "before": {...}, "after": {...},
        "before_hash", "after_hash",
        "metadata": {...},
        "created_at": datetime,
    }

Older records written in the flat shape (actor_user_id / entity_type / entity_id)
are still read by the admin audit service; nothing new is written that way.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId

from core.database import get_rag_db

logger = logging.getLogger(__name__)

AUDIT_SCHEMA_VERSION = 2


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ref(value: Any) -> Any:
    """Store ids as ObjectId when they look like one, so lookups by id are uniform."""
    if value is None or isinstance(value, ObjectId):
        return value
    text = str(value)
    return ObjectId(text) if ObjectId.is_valid(text) else text


def _diff(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    changes = []
    for key in sorted({*before, *after}, key=str):
        if before.get(key) != after.get(key):
            changes.append({"path": str(key), "old_value": before.get(key), "new_value": after.get(key)})
    return changes


def build_audit_event(
    *,
    action: str,
    entity_type: str,
    entity_id: Any = None,
    entity_version_id: Any = None,
    actor_user_id: Any = None,
    actor_role: str | None = None,
    actor_type: str | None = None,
    service_name: str | None = None,
    model_id: Any = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    changes: list[dict[str, Any]] | None = None,
    before_hash: str | None = None,
    after_hash: str | None = None,
    metadata: dict[str, Any] | None = None,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    before = before or {}
    after = after or {}
    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "action": action,
        "actor": {
            "type": actor_type or ("USER" if actor_user_id is not None else "SYSTEM"),
            "user_id": _ref(actor_user_id),
            "role": actor_role,
            "model_id": _ref(model_id),
            "service_name": service_name,
        },
        "entity": {
            "type": str(entity_type).lower(),
            "id": _ref(entity_id),
            "version_id": _ref(entity_version_id),
        },
        "changes": changes if changes is not None else _diff(before, after),
        "before": before,
        "after": after,
        "before_hash": before_hash,
        "after_hash": after_hash,
        "metadata": metadata or {},
        "created_at": created_at or utc_now(),
    }


def write_audit_event(database, *, session=None, **fields: Any) -> dict[str, Any]:
    """Insert an audit event; errors propagate so callers inside a transaction roll back."""
    event = build_audit_event(**fields)
    if session is not None:
        database.audit_logs.insert_one(event, session=session)
    else:
        database.audit_logs.insert_one(event)
    return event


def record_audit_event(**fields: Any) -> None:
    """Best-effort audit write for request handlers that must not fail on logging."""
    action = fields.get("action")
    try:
        write_audit_event(get_rag_db(), **fields)
    except Exception as exc:
        logger.warning("Failed to write audit event %s: %s", action, exc)
