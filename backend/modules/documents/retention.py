from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable
from pathlib import Path

from modules.documents.storage import LocalArtifactStorage


@dataclass(frozen=True)
class RetentionPolicy:
    hot_days: int = 30
    cold_days: int = 365

    def __post_init__(self) -> None:
        if self.hot_days < 0 or self.cold_days < self.hot_days:
            raise ValueError("Retention requires 0 <= hot_days <= cold_days")


def deduplicate_artifact_file(source: str | Path, blob_root: str | Path) -> dict:
    """Move a new artifact into content-addressed local storage, reusing an identical blob."""
    return LocalArtifactStorage(blob_root).save_content_addressed(source)


def protected_artifact_ids(document: dict, lineage_records: Iterable[dict] = ()) -> set[str]:
    """Collect artifacts that cannot be archived/deleted under any automatic policy."""
    protected: set[str] = set()
    active_job_ids = {
        str(value)
        for value in {
            *((document.get("current_processing") or {}).values()),
            *((document.get("pending_processing") or {}).values()),
        }
        if value is not None
    }
    for artifact in document.get("artifacts") or []:
        artifact_id = str(artifact.get("_id") or "")
        if artifact.get("is_current") or str(artifact.get("job_id") or "") in active_job_ids:
            protected.add(artifact_id)
    for record in lineage_records:
        for snapshot_key in ("from_snapshot", "to_snapshot", "rollback_snapshot"):
            snapshot = record.get(snapshot_key) or {}
            protected.update(str(value) for value in snapshot.get("artifact_ids") or [])
    return protected


def build_retention_plan(
    artifacts: Iterable[dict],
    *,
    protected_ids: set[str],
    policy: RetentionPolicy,
    now: datetime | None = None,
) -> dict:
    """Return a non-mutating hot/cold/delete plan with hash-based dedup groups."""
    now = now or datetime.now(timezone.utc)
    hot_cutoff = now - timedelta(days=policy.hot_days)
    cold_cutoff = now - timedelta(days=policy.cold_days)
    plan = {"keep_hot": [], "archive_cold": [], "delete_candidates": [], "dedup_groups": []}
    by_hash: dict[str, list[str]] = defaultdict(list)
    for artifact in artifacts:
        artifact_id = str(artifact.get("_id") or "")
        digest = str(artifact.get("sha256") or "")
        created_at = artifact.get("created_at") or now
        if digest:
            by_hash[digest].append(artifact_id)
        if artifact_id in protected_ids or created_at >= hot_cutoff:
            plan["keep_hot"].append(artifact_id)
        elif created_at >= cold_cutoff:
            plan["archive_cold"].append(artifact_id)
        else:
            plan["delete_candidates"].append(
                {"artifact_id": artifact_id, "requires_explicit_confirmation": True}
            )
    plan["dedup_groups"] = [
        {"sha256": digest, "canonical_artifact_id": ids[0], "duplicate_artifact_ids": ids[1:]}
        for digest, ids in by_hash.items()
        if len(ids) > 1
    ]
    return plan
