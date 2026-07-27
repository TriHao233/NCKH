from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId

from core.database import get_rag_db

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def record_audit_event(
    *,
    action: str,
    entity_type: str,
    entity_id: str | ObjectId | None = None,
    actor_user_id: str | ObjectId | None = None,
    actor_role: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    try:
        get_rag_db().audit_logs.insert_one(
            {
                "action": action,
                "entity_type": entity_type,
                "entity_id": str(entity_id) if entity_id is not None else None,
                "actor_user_id": str(actor_user_id) if actor_user_id is not None else None,
                "actor_role": actor_role,
                "before": before or {},
                "after": after or {},
                "metadata": metadata or {},
                "created_at": utc_now(),
            }
        )
    except Exception as exc:
        logger.warning("Failed to write audit event %s: %s", action, exc)
