"""Generate denominator-preserving holdout/human-review metrics from JSONL records."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def build_report(rows: list[dict], *, split: str, model_digest: str) -> dict:
    evaluated = [row for row in rows if row.get("decision") in {"PASS", "FAIL"}]
    pass_count = sum(row["decision"] == "PASS" for row in evaluated)
    by_reason = {}
    for row in evaluated:
        if row["decision"] == "FAIL":
            reason = row.get("error_category") or "UNCLASSIFIED"
            by_reason[reason] = by_reason.get(reason, 0) + 1
    reviewers = {str(row["reviewer_id"]) for row in rows if row.get("reviewer_id")}
    payload = {
        "split": split,
        "model_digest": model_digest,
        "denominator": len(rows),
        "evaluated": len(evaluated),
        "excluded": len(rows) - len(evaluated),
        "pass_count": pass_count,
        "pass_rate": round(pass_count / len(evaluated), 4) if evaluated else None,
        "reviewer_count": len(reviewers),
        "failures_by_category": by_reason,
    }
    payload["report_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--split", required=True)
    parser.add_argument("--model-digest", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = [
        json.loads(line)
        for line in args.input.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    args.output.write_text(
        json.dumps(
            build_report(rows, split=args.split, model_digest=args.model_digest),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
