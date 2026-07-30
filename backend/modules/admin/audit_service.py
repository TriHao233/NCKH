from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from bson import ObjectId
from pymongo.database import Database


REDACTED_VALUE = "[REDACTED]"
SENSITIVE_FIELD_NAMES = {
    "authorization",
    "credential",
    "credentials",
    "id_token",
    "refresh_token",
    "access_token",
    "api_key",
    "private_key",
    "client_secret",
    "wstoken",
}


def _is_sensitive_field(value: Any) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    return (
        normalized in SENSITIVE_FIELD_NAMES
        or "password" in normalized
        or "secret" in normalized
        or normalized.endswith("_token")
    )


def _redact_sensitive(value: Any):
    if isinstance(value, dict):
        sensitive_change = _is_sensitive_field(value.get("path") or value.get("field"))
        redacted = {}
        for key, item in value.items():
            if _is_sensitive_field(key) or (
                sensitive_change
                and key in {"old_value", "new_value", "value", "before", "after"}
            ):
                redacted[key] = REDACTED_VALUE
            else:
                redacted[key] = _redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    return value


def _json_safe(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _object_id_candidates(value: str) -> list[Any]:
    candidates: list[Any] = [value]
    try:
        candidates.append(ObjectId(value))
    except Exception:
        pass
    return candidates


def _normalize_audit_log(record: dict) -> dict:
    actor = record.get("actor") or {}
    entity = record.get("entity") or {}
    actor_user_id = record.get("actor_user_id") or actor.get("user_id")
    entity_id = record.get("entity_id") or entity.get("id")
    return {
        "id": str(record["_id"]),
        "action": record.get("action") or "UNKNOWN",
        "actor": {
            "type": actor.get("type") or ("USER" if actor_user_id else None),
            "user_id": str(actor_user_id) if actor_user_id is not None else None,
            "role": record.get("actor_role") or actor.get("role"),
            "model_id": str(actor.get("model_id")) if actor.get("model_id") is not None else None,
            "service_name": actor.get("service_name"),
        },
        "entity": {
            "type": record.get("entity_type") or entity.get("type"),
            "id": str(entity_id) if entity_id is not None else None,
            "version_id": str(entity.get("version_id")) if entity.get("version_id") is not None else None,
        },
        "before": _json_safe(_redact_sensitive(record.get("before") or {})),
        "after": _json_safe(_redact_sensitive(record.get("after") or {})),
        "changes": _json_safe(_redact_sensitive(record.get("changes") or [])),
        "metadata": _json_safe(_redact_sensitive(record.get("metadata") or {})),
        "before_hash": record.get("before_hash"),
        "after_hash": record.get("after_hash"),
        "created_at": record.get("created_at"),
    }


class AdminAuditService:
    def __init__(self, database: Database):
        self.db = database

    def list(
        self,
        *,
        page: int,
        page_size: int,
        actor_user_id: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        action: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        search: str | None = None,
    ) -> dict:
        clauses: list[dict] = []
        if actor_user_id:
            clauses.append(
                {
                    "$or": [
                        {"actor_user_id": actor_user_id},
                        {"actor.user_id": {"$in": _object_id_candidates(actor_user_id)}},
                    ]
                }
            )
        if entity_type:
            entity_values = list({entity_type, entity_type.upper(), entity_type.lower()})
            clauses.append(
                {
                    "$or": [
                        {"entity_type": {"$in": entity_values}},
                        {"entity.type": {"$in": entity_values}},
                    ]
                }
            )
        if entity_id:
            clauses.append(
                {
                    "$or": [
                        {"entity_id": entity_id},
                        {"entity.id": {"$in": _object_id_candidates(entity_id)}},
                    ]
                }
            )
        if action:
            clauses.append({"action": action})
        if date_from or date_to:
            created_at: dict[str, datetime] = {}
            if date_from:
                created_at["$gte"] = date_from
            if date_to:
                created_at["$lte"] = date_to
            clauses.append({"created_at": created_at})
        if search:
            regex = {"$regex": re.escape(search), "$options": "i"}
            clauses.append(
                {
                    "$or": [
                        {"action": regex},
                        {"actor_user_id": regex},
                        {"actor_role": regex},
                        {"entity_type": regex},
                        {"entity_id": regex},
                        {"actor.service_name": regex},
                        {"entity.type": regex},
                        {"before.status": regex},
                        {"before.role": regex},
                        {"after.status": regex},
                        {"after.role": regex},
                        {"changes.field": regex},
                        {"metadata.reason": regex},
                        {"metadata.message": regex},
                        {"metadata.error": regex},
                    ]
                }
            )

        match = {"$and": clauses} if len(clauses) > 1 else (clauses[0] if clauses else {})
        total = self.db.audit_logs.count_documents(match)
        cursor = (
            self.db.audit_logs.find(match)
            .sort("created_at", -1)
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        return {
            "items": [_normalize_audit_log(record) for record in cursor],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
