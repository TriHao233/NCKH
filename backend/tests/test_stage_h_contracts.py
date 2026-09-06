from core import health
from core.health import operational_alerts
from core.acceptance import build_holdout_report


def test_alerts_cover_expired_lease_dead_letter_queue_age_and_moodle_unknown():
    metrics = {
        "queues": {"generation": {"expired_leases": 1, "dead_lettered": 2, "oldest_queued_seconds": 901}},
        "moodle": {"unknown": 1},
    }
    assert {item["code"] for item in operational_alerts(metrics)} == {
        "EXPIRED_LEASE",
        "DEAD_LETTER",
        "QUEUE_AGE",
        "MOODLE_UNKNOWN",
    }


def test_holdout_report_keeps_exclusions_and_model_provenance():
    report = build_holdout_report(
        [
            {"decision": "PASS", "reviewer_id": "r1"},
            {"decision": "FAIL", "reviewer_id": "r2", "error_category": "GROUNDING"},
            {"decision": "EXCLUDED", "reviewer_id": "r1"},
        ],
        split="holdout",
        model_digest="sha256:model",
    )
    assert report["denominator"] == 3
    assert report["evaluated"] == 2
    assert report["excluded"] == 1
    assert report["pass_rate"] == 0.5
    assert report["failures_by_category"] == {"GROUNDING": 1}
    assert report["model_digest"] == "sha256:model"
    assert report["report_sha256"]


def test_readiness_fails_closed_when_required_transactions_are_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(health, "ping_database", lambda: None)
    monkeypatch.setattr(health, "supports_transactions", lambda: False)
    monkeypatch.setattr(health.settings, "require_mongo_transactions", True)
    monkeypatch.setattr(health.settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(health.settings, "metadata_dir", str(tmp_path))
    ready, report = health.readiness_report()
    assert ready is False
    assert report["status"] == "not_ready"
    assert report["checks"]["transactions"]["ok"] is False
