from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path

from core.config import resolve_path, settings
from core.database import ping_database, supports_transactions


def readiness_report() -> tuple[bool, dict]:
    checks = {}
    try:
        ping_database()
        checks["mongodb"] = {"ok": True}
    except Exception as exc:
        checks["mongodb"] = {"ok": False, "error": type(exc).__name__}
    transactions = supports_transactions() if checks["mongodb"]["ok"] else False
    checks["transactions"] = {
        "ok": transactions or not settings.require_mongo_transactions,
        "required": settings.require_mongo_transactions,
        "supported": transactions,
    }
    paths = [resolve_path(settings.upload_dir), resolve_path(settings.metadata_dir)]
    for path in paths:
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    checks["storage"] = {
        "ok": all(Path(path).exists() and Path(path).is_dir() and os.access(path, os.W_OK) for path in paths),
        "paths": [str(path) for path in paths],
    }
    checks["inference_policy"] = {
        "ok": settings.inference_policy == "LOCAL_ONLY" or settings.app_env != "production",
        "value": settings.inference_policy,
    }
    ready = all(check["ok"] for check in checks.values())
    return ready, {
        "status": "ready" if ready else "not_ready",
        "observed_at": datetime.now(timezone.utc),
        "checks": checks,
    }


def operational_alerts(metrics: dict) -> list[dict]:
    alerts = []
    for queue_name, queue in metrics.get("queues", {}).items():
        if queue.get("expired_leases", 0) > 0:
            alerts.append({"code": "EXPIRED_LEASE", "severity": "critical", "queue": queue_name})
        if queue.get("dead_lettered", 0) > 0:
            alerts.append({"code": "DEAD_LETTER", "severity": "warning", "queue": queue_name})
        if (queue.get("oldest_queued_seconds") or 0) > 900:
            alerts.append({"code": "QUEUE_AGE", "severity": "warning", "queue": queue_name})
    moodle = metrics.get("moodle", {})
    if moodle.get("unknown", 0) > 0:
        alerts.append({"code": "MOODLE_UNKNOWN", "severity": "critical", "count": moodle["unknown"]})
    return alerts
