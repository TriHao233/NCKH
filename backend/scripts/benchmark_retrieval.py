"""Run the Stage-D dense/lexical/hybrid retrieval benchmark on a licensed query set.

The input is JSON: {"queries": [{"document_id": "...", "query": "...",
"target_heading": "...", "expected_chunk_ids": ["..."]}]}. Reindex with each
candidate EMBEDDING_MODEL_NAME before running so every report is tied to a model digest.
"""

import argparse
import hashlib
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from core.config import settings
from core.database import get_database
from modules.rag.mongodb import embedding_model_manifest
from modules.rag.search import get_context_snapshot


def recall_at_k(retrieved: list[str], expected: list[str]) -> float:
    expected_set = {str(item) for item in expected if item}
    if not expected_set:
        return 0.0
    return len(expected_set & {str(item) for item in retrieved}) / len(expected_set)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * percentile))
    return ordered[index]


def run_benchmark(payload: dict, *, limit: int = 5) -> dict:
    queries = payload.get("queries") or []
    if not queries:
        raise ValueError("Benchmark phải có ít nhất một query")
    modes = ("dense", "lexical", "hybrid")
    rows = []
    for query_index, item in enumerate(queries, start=1):
        for mode in modes:
            started = time.perf_counter()
            error = None
            result = None
            try:
                result = get_context_snapshot(
                    document_id=str(item["document_id"]),
                    collection_name=str(
                        item.get("collection_name") or settings.chromadb_collection_name
                    ),
                    target_heading=item.get("target_heading"),
                    query_text=str(item.get("query") or ""),
                    limit=limit,
                    retrieval_mode=mode,
                )
            except Exception as exc:
                error = str(exc)
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            retrieved = [
                str(row.get("chunk_id"))
                for row in ((result or {}).get("results") or [])
                if row.get("chunk_id")
            ]
            rows.append(
                {
                    "query_index": query_index,
                    "query_type": item.get("query_type") or "unspecified",
                    "mode": mode,
                    "recall_at_k": recall_at_k(
                        retrieved,
                        item.get("expected_chunk_ids") or [],
                    ),
                    "latency_ms": latency_ms,
                    "retrieved_chunk_ids": retrieved,
                    "error": error,
                    "trace": (result or {}).get("trace") or {},
                }
            )
    summary = {}
    for mode in modes:
        mode_rows = [row for row in rows if row["mode"] == mode]
        recalls = [row["recall_at_k"] for row in mode_rows]
        latencies = [row["latency_ms"] for row in mode_rows]
        summary[mode] = {
            "query_count": len(mode_rows),
            "mean_recall_at_k": round(statistics.mean(recalls), 4),
            "p50_latency_ms": _percentile(latencies, 0.5),
            "p95_latency_ms": _percentile(latencies, 0.95),
            "error_count": sum(bool(row["error"]) for row in mode_rows),
        }
    collection_names = sorted(
        {
            str(item.get("collection_name") or settings.chromadb_collection_name)
            for item in queries
        }
    )
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "limit": limit,
        "embedding_manifests": [
            embedding_model_manifest(collection_name)
            for collection_name in collection_names
        ],
        "summary": summary,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--persist", action="store_true")
    parser.add_argument("--min-hybrid-recall", type=float, default=0.85)
    args = parser.parse_args()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    raw = input_path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    report = run_benchmark(payload, limit=max(1, args.limit))
    report["fixture"] = {
        "path": str(input_path),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    report["gate"] = {
        "target_recall_at_k": args.min_hybrid_recall,
        "passed": report["summary"]["hybrid"]["mean_recall_at_k"]
        >= args.min_hybrid_recall,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.persist:
        get_database().retrieval_benchmarks.insert_one(report)
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if report["gate"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
