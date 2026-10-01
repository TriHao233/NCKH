"""Atomic provider concurrency leases shared by all PostgreSQL-backed workers."""

from __future__ import annotations

from core.config import settings
from core.postgres import postgres_connection


def _parts(slot_id: str) -> tuple[str, int]:
    provider, index = slot_id.rsplit(":", 1)
    return provider, int(index)


def try_acquire(group: str, holder_id: str, limit: int) -> str | None:
    with postgres_connection() as conn:
        conn.execute(
            """INSERT INTO llm_slots (provider, slot_index, updated_at)
               SELECT %s, index, now() FROM generate_series(0, %s) AS index
               ON CONFLICT (provider, slot_index) DO NOTHING""",
            (group, limit - 1),
        )
        row = conn.execute(
            """WITH available AS (
                   SELECT provider, slot_index FROM llm_slots
                   WHERE provider=%s AND slot_index < %s
                     AND (holder_id IS NULL OR lease_expires_at IS NULL
                          OR lease_expires_at <= now() OR holder_id=%s)
                   ORDER BY slot_index LIMIT 1 FOR UPDATE SKIP LOCKED
               )
               UPDATE llm_slots AS slot
               SET holder_id=%s,
                   lease_expires_at=now() + (%s * interval '1 second'),
                   updated_at=now()
               FROM available
               WHERE slot.provider=available.provider
                 AND slot.slot_index=available.slot_index
               RETURNING slot.slot_index""",
            (group, limit, holder_id, holder_id, settings.llm_slot_lease_seconds),
        ).fetchone()
    return f"{group}:{row['slot_index']}" if row else None


def heartbeat(slot_id: str, holder_id: str) -> bool:
    provider, index = _parts(slot_id)
    with postgres_connection() as conn:
        row = conn.execute(
            """UPDATE llm_slots SET
                   lease_expires_at=now() + (%s * interval '1 second'), updated_at=now()
               WHERE provider=%s AND slot_index=%s AND holder_id=%s
               RETURNING slot_index""",
            (settings.llm_slot_lease_seconds, provider, index, holder_id),
        ).fetchone()
    return row is not None


def release(slot_id: str, holder_id: str) -> None:
    provider, index = _parts(slot_id)
    with postgres_connection() as conn:
        conn.execute(
            """UPDATE llm_slots SET holder_id=NULL, lease_expires_at=NULL, updated_at=now()
               WHERE provider=%s AND slot_index=%s AND holder_id=%s""",
            (provider, index, holder_id),
        )


def counts() -> dict[str, int]:
    with postgres_connection() as conn:
        row = conn.execute(
            """SELECT
                   count(*) FILTER (WHERE holder_id IS NOT NULL
                       AND lease_expires_at > now()) AS in_use,
                   count(*) FILTER (WHERE holder_id IS NOT NULL
                       AND lease_expires_at <= now()) AS expired
               FROM llm_slots"""
        ).fetchone()
    return {"in_use": row["in_use"], "expired": row["expired"]}
