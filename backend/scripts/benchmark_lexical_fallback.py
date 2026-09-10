from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from modules.rag import search


DEFAULT_QUERIES = [
    "FIFO",
    "LIFO",
    "cây nhị phân tìm kiếm",
    "duyệt đồ thị theo chiều rộng",
    "độ phức tạp của thuật toán",
    "hàng đợi ưu tiên",
]


def _run(document_id: str, collection: str, query: str) -> tuple[float, dict]:
    started = time.perf_counter()
    result = search.get_context_snapshot(
        document_id=document_id,
        collection_name=collection,
        query_text=query,
        limit=5,
    )
    return (time.perf_counter() - started) * 1000, result


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare bounded conditional lexical fallback with always-on fallback")
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--query", action="append", default=[])
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--output-report", type=Path)
    args = parser.parse_args()
    queries = args.query or DEFAULT_QUERIES
    original_policy = search._requires_lexical_fallback
    samples: dict[str, dict[str, list]] = {
        query: {"always_ms": [], "conditional_ms": [], "always_ids": [], "conditional_ids": []}
        for query in queries
    }

    try:
        search._requires_lexical_fallback = original_policy
        _run(args.document_id, args.collection, queries[0])
        for iteration in range(max(1, args.iterations)):
            for query in queries:
                modes = ("always", "conditional") if iteration % 2 == 0 else ("conditional", "always")
                for mode in modes:
                    search._requires_lexical_fallback = (
                        (lambda _text, _distances: True) if mode == "always" else original_policy
                    )
                    elapsed, result = _run(args.document_id, args.collection, query)
                    samples[query][f"{mode}_ms"].append(round(elapsed, 3))
                    samples[query][f"{mode}_ids"] = [item.get("chunk_id") for item in result["results"]]
                    samples[query][f"{mode}_provenance"] = [
                        bool(item.get("chunk_id") and item.get("source_uri") and item.get("page_marks"))
                        for item in result["results"]
                    ]
    finally:
        search._requires_lexical_fallback = original_policy

    details = []
    for query, values in samples.items():
        always_ids = values["always_ids"]
        conditional_ids = values["conditional_ids"]
        overlap = len(set(always_ids) & set(conditional_ids)) / max(len(set(always_ids)), 1)
        details.append(
            {
                "query": query,
                "always_median_ms": round(statistics.median(values["always_ms"]), 3),
                "conditional_median_ms": round(statistics.median(values["conditional_ms"]), 3),
                "top_5_overlap": round(overlap, 4),
                "top_1_same": bool(always_ids and conditional_ids and always_ids[0] == conditional_ids[0]),
                "conditional_provenance_complete": all(values.get("conditional_provenance") or []),
                "always_ids": always_ids,
                "conditional_ids": conditional_ids,
            }
        )
    all_always = [elapsed for values in samples.values() for elapsed in values["always_ms"]]
    all_conditional = [elapsed for values in samples.values() for elapsed in values["conditional_ms"]]
    always_median = statistics.median(all_always)
    conditional_median = statistics.median(all_conditional)
    report = {
        "document_id": args.document_id,
        "collection": args.collection,
        "iterations": max(1, args.iterations),
        "query_count": len(queries),
        "always_on_median_ms": round(always_median, 3),
        "conditional_median_ms": round(conditional_median, 3),
        "latency_change_percent": round((conditional_median / max(always_median, 0.001) - 1.0) * 100.0, 3),
        "mean_top_5_overlap": round(statistics.mean(item["top_5_overlap"] for item in details), 4),
        "top_1_retention": round(statistics.mean(item["top_1_same"] for item in details), 4),
        "provenance_completeness": round(
            statistics.mean(item["conditional_provenance_complete"] for item in details), 4
        ),
        "note": "Overlap is a regression signal, not independent relevance ground truth.",
        "details": details,
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output_report:
        args.output_report.parent.mkdir(parents=True, exist_ok=True)
        args.output_report.write_text(payload, encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
