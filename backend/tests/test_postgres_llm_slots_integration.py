"""Run with RUN_POSTGRES_INTEGRATION=1 and POSTGRES_DSN on a test database."""

import os
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from core.config import settings
from core.postgres import postgres_connection
from modules.admin.job_metrics import collect_job_metrics
from modules.generation.llm.concurrency import (
    _heartbeat_slot, _release_slot, _try_acquire_slot,
)
from modules.generation.llm.postgres_slots import counts


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1" or not settings.postgres_dsn,
    reason="Requires an explicitly configured PostgreSQL test database",
)


def test_postgres_slot_is_exclusive_reclaimable_and_owner_checked(monkeypatch):
    monkeypatch.setattr(settings, "llm_slot_store", "postgres")
    group = f"provider:test-{uuid4().hex[:12]}"
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            acquired = list(executor.map(
                lambda holder: _try_acquire_slot(group, holder, 1),
                ("holder-a", "holder-b"),
            ))
        assert sum(slot is not None for slot in acquired) == 1
        owner = "holder-a" if acquired[0] else "holder-b"
        other = "holder-b" if owner == "holder-a" else "holder-a"
        slot = next(item for item in acquired if item)
        assert slot == f"{group}:0"
        assert counts()["in_use"] >= 1
        metrics_db = MagicMock()
        metrics_db.generation_jobs.find_one.return_value = None
        metrics_db.evaluation_jobs.find_one.return_value = None
        metrics_db.document_jobs.find_one.return_value = None
        assert collect_job_metrics(metrics_db)["llm_slots"]["in_use"] >= 1
        metrics_db.llm_slots.count_documents.assert_not_called()
        assert _heartbeat_slot(slot, other) is False
        _release_slot(slot, other)
        assert _try_acquire_slot(group, other, 1) is None
        assert _heartbeat_slot(slot, owner) is True

        with postgres_connection() as conn:
            conn.execute(
                "UPDATE llm_slots SET lease_expires_at=now() - interval '1 second' "
                "WHERE provider=%s", (group,),
            )
        assert counts()["expired"] >= 1
        assert _try_acquire_slot(group, other, 1) == slot
        assert _heartbeat_slot(slot, owner) is False
        _release_slot(slot, other)
        assert _try_acquire_slot(group, owner, 1) == slot
    finally:
        with postgres_connection() as conn:
            conn.execute("DELETE FROM llm_slots WHERE provider=%s", (group,))
