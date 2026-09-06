import hashlib
import json


def build_holdout_report(rows: list[dict], *, split: str, model_digest: str) -> dict:
    evaluated = [row for row in rows if row.get("decision") in {"PASS", "FAIL"}]
    pass_count = sum(row["decision"] == "PASS" for row in evaluated)
    failures = {}
    for row in evaluated:
        if row["decision"] == "FAIL":
            category = row.get("error_category") or "UNCLASSIFIED"
            failures[category] = failures.get(category, 0) + 1
    payload = {
        "split": split,
        "model_digest": model_digest,
        "denominator": len(rows),
        "evaluated": len(evaluated),
        "excluded": len(rows) - len(evaluated),
        "pass_count": pass_count,
        "pass_rate": round(pass_count / len(evaluated), 4) if evaluated else None,
        "reviewer_count": len({str(row["reviewer_id"]) for row in rows if row.get("reviewer_id")}),
        "failures_by_category": failures,
    }
    payload["report_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return payload
