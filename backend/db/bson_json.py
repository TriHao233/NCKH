"""Restore BSON-shaped IDs and timestamps from PostgreSQL JSONB payloads."""

from datetime import datetime

from bson import ObjectId


# Ids the ingest parsers derive from content (sha256 prefix, 24 hex characters). They look
# like ObjectIds but are plain strings everywhere else: converting them breaks chunk
# metadata, which is JSON-encoded for the vector store.
HASH_ID_KEYS = frozenset({"block_id", "asset_id"})


def restore(value, key: str = ""):
    if isinstance(value, dict):
        return {name: restore(item, name) for name, item in value.items()}
    if isinstance(value, list):
        return [restore(item, key[:-1] if key.endswith("s") else key) for item in value]
    if (
        isinstance(value, str)
        and key not in HASH_ID_KEYS
        and (key in {"_id", "id"} or key.endswith("_id"))
    ):
        return ObjectId(value) if ObjectId.is_valid(value) else value
    if isinstance(value, str) and key.endswith("_at"):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return value
