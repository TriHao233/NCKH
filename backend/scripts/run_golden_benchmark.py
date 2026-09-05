from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from modules.documents.ingest.benchmark import evaluate_golden_case, load_golden_case
from modules.ocr.pipeline import run_document_pipeline


DEFAULT_CORPUS = BACKEND_DIR / "tests" / "golden_corpus" / "v1"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run extraction against independent golden truth")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--generated-dir", type=Path)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--output-report", type=Path)
    args = parser.parse_args()
    manifest = json.loads((args.corpus / "manifest.json").read_text(encoding="utf-8"))
    selected = [case for case in manifest["cases"] if not args.case or case["id"] in args.case]
    reports = []
    with tempfile.TemporaryDirectory(prefix="qbank-golden-output-") as temp_dir:
        for case in selected:
            relative_input = Path(case["input"])
            if relative_input.parts[0] == "generated":
                if not args.generated_dir:
                    reports.append({"case_id": case["id"], "status": "skipped", "reason": "--generated-dir missing"})
                    continue
                source = args.generated_dir / relative_input.name
            else:
                source = args.corpus / relative_input
            if not source.exists():
                reports.append({"case_id": case["id"], "status": "skipped", "reason": f"input missing: {source}"})
                continue
            _case, expected = load_golden_case(args.corpus, case["id"])
            output = Path(temp_dir) / f"{case['id']}.md"
            tracemalloc.start()
            cpu_started = time.process_time()
            wall_started = time.perf_counter()
            try:
                result = run_document_pipeline(
                    str(source),
                    str(output),
                    document_title=case["id"],
                    document_id=f"golden-{case['id']}",
                    source_file_name=source.name,
                    source_uri=f"golden://v1/{source.name}",
                )
                evaluation = evaluate_golden_case(expected, result["pages"], case["profile"])
                evaluation.update(
                    {
                        "case_id": case["id"],
                        "performance": {
                            "wall_ms": round((time.perf_counter() - wall_started) * 1000, 2),
                            "cpu_ms": round((time.process_time() - cpu_started) * 1000, 2),
                            "python_peak_ram_bytes": tracemalloc.get_traced_memory()[1],
                            "markdown_bytes": Path(result["output_file"]).stat().st_size,
                            "raw_artifact_bytes": Path(result["raw_extraction_file"]).stat().st_size,
                        },
                        "pipeline_stats": result["stats"],
                    }
                )
                reports.append(evaluation)
            except Exception as exc:
                reports.append({
                    "case_id": case["id"],
                    "status": "failed",
                    "reason": f"{type(exc).__name__}: {exc}",
                    "performance": {"wall_ms": round((time.perf_counter() - wall_started) * 1000, 2)},
                })
            finally:
                tracemalloc.stop()
    summary = {
        "corpus_version": manifest["corpus_version"],
        "independent_ground_truth": True,
        "reports": reports,
        "counts": {
            status: sum(report.get("status") == status for report in reports)
            for status in ("passed", "needs_review", "failed", "skipped")
        },
    }
    payload = json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    if args.output_report:
        args.output_report.parent.mkdir(parents=True, exist_ok=True)
        args.output_report.write_text(payload, encoding="utf-8")
    print(payload)
    return 0 if summary["counts"]["failed"] == 0 and summary["counts"]["needs_review"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
