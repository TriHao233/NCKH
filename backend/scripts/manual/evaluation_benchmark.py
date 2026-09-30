"""Run the AI evaluation prompt against a real model on labelled questions.

Each case in the fixture is labelled PASS (a correct, grounded question the
evaluator should let through) or BLOCK (a wrong or unsupported question it must
never approve). Source chunks are supplied directly, so retrieval quality is not
measured here; this only measures the prompt + model + guardrail pipeline.

    cd backend
    python scripts/manual/evaluation_benchmark.py --model qwen3-8b
    python scripts/manual/evaluation_benchmark.py --model deepseek --only mcq_queue_correct
"""

import argparse
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))

from modules.generation.llm.factory import _provider_from_snapshot  # noqa: E402
from modules.generation.llm.model_registry import (  # noqa: E402
    EVALUATION_CAPABILITY,
    resolve_direct_model_snapshot,
)
from modules.questions.workflow_service import (  # noqa: E402
    DEFAULT_THRESHOLDS,
    DEFAULT_WEIGHTS,
    QuestionWorkflowService,
    _limit_evaluation_output,
    _prepare_evaluation_attempt,
)

DEFAULT_CASES = BASE_DIR / "tests" / "fixtures" / "evaluation_benchmark_cases.json"
POLICY = {"name": "benchmark", "version": 1, "weights": DEFAULT_WEIGHTS, "thresholds": DEFAULT_THRESHOLDS}


def _build_case(case: dict, sources: dict) -> tuple[dict, dict, list[dict], dict]:
    excerpt = sources[case["source"]]
    chunk_id = hashlib.sha1(case["source"].encode()).hexdigest()[:24]
    source_chunks = [
        {
            "chunk_id": chunk_id,
            "content_hash": hashlib.sha256(excerpt.encode()).hexdigest(),
            "label": "S1",
            "citation_order": 1,
            "is_primary": True,
            "excerpt": excerpt,
            "similarity": 0.9,
        }
    ]
    question_data = {
        "correct_answer": case["correct_answer"],
        "explanation": case.get("explanation", ""),
    }
    if case.get("options"):
        question_data["options"] = case["options"]
    version = {
        "_id": f"v-{case['name']}",
        "content": case["question"],
        "document_id": "benchmark-document",
        "classification": {
            "assessment_type": case["type"],
            "bloom": {"level": case["bloom"]},
            "difficulty": "de",
        },
        "clos": [] if case.get("no_clo") else [
            {"code": "CLO1", "description": "Trình bày và vận dụng các cấu trúc dữ liệu cơ bản."}
        ],
        "question_data": question_data,
    }
    grounded_version = {
        **version,
        "sources": [
            {
                "chunk_id": chunk_id,
                "chunk_content_hash": source_chunks[0]["content_hash"],
                "citation_order": 1,
                "is_primary": True,
                "context_excerpt": excerpt,
            }
        ],
    }
    question = {"_id": f"q-{case['name']}", "question_code": case["name"]}
    return question, version, source_chunks, grounded_version


def _passed(scores, feedback: dict, evidence: dict) -> tuple[bool, float]:
    """Mirror QuestionWorkflowService.evaluate() pass decision."""
    overall = round(sum(getattr(scores, key) * DEFAULT_WEIGHTS[key] for key in DEFAULT_WEIGHTS), 4)
    action = str(feedback.get("action") or "").upper()
    passed = (
        overall >= DEFAULT_THRESHOLDS["pass_min"]
        and action not in {"NEEDS_REVISION", "REJECT"}
        and str(feedback.get("severity") or "").upper() != "HIGH"
        and not evidence.get("unsupported_claims")
    )
    return passed, overall


async def _run_case(service, case, sources, model_snapshot, max_attempts):
    question, version, source_chunks, grounded_version = _build_case(case, sources)
    prompt, prompt_snapshot, _ = service._build_evaluation_prompt(
        question, version, POLICY, source_chunks=source_chunks
    )
    attempts = []
    for attempt in range(1, max_attempts + 1):
        attempt_prompt, _, snapshot = _prepare_evaluation_attempt(
            prompt, prompt_snapshot, model_snapshot, attempt
        )
        # Call the provider directly: the slot limiter needs the database.
        llm = _provider_from_snapshot(snapshot).wrapped
        started = time.perf_counter()
        raw = ""
        try:
            raw = await llm.generate_text(attempt_prompt)
            scores, feedback, evidence = service._finalize_llm_evaluation(
                raw, source_chunks, grounded_version, POLICY, llm=llm
            )
        except Exception as exc:  # noqa: BLE001 - benchmark records every failure
            attempts.append({
                "attempt": attempt,
                "seconds": round(time.perf_counter() - started, 1),
                "error": f"{type(exc).__name__}: {exc}"[:300],
                "output": QuestionWorkflowService._llm_output_metadata(llm, raw),
                "raw_tail": raw[-300:],
            })
            continue
        passed, overall = _passed(scores, feedback, evidence)
        attempts.append({
            "attempt": attempt,
            "seconds": round(time.perf_counter() - started, 1),
            "output": evidence.get("model_output"),
        })
        return {
            "name": case["name"],
            "expect": case["expect"],
            "passed": passed,
            "correct": passed == (case["expect"] == "PASS"),
            "overall": overall,
            "scores": scores.model_dump(),
            "action": feedback.get("action"),
            "severity": feedback.get("severity"),
            "summary": feedback.get("summary"),
            "missing": feedback.get("missing"),
            "unsupported_claims": evidence.get("unsupported_claims"),
            "answer_guardrail_issues": (evidence.get("answer_guardrail") or {}).get("issues"),
            "metadata_guardrail_issues": (evidence.get("metadata_guardrail") or {}).get("issues"),
            "model_contradictions": (evidence.get("consistency") or {}).get("model_contradictions"),
            "normalized": bool(evidence.get("decision_normalization")),
            "assessed_difficulty": evidence.get("assessed_difficulty"),
            "attempts": attempts,
            "raw_response": raw,
        }
    return {
        "name": case["name"],
        "expect": case["expect"],
        "passed": False,
        "error": True,
        # A failed evaluation never approves, but it also gives the reviewer nothing.
        "correct": None,
        "attempts": attempts,
    }


def _report(results: list[dict], model_code: str) -> dict:
    graded = [item for item in results if not item.get("error")]
    errors = [item for item in results if item.get("error")]
    false_approve = [item["name"] for item in graded if item["expect"] == "BLOCK" and item["passed"]]
    false_block = [item["name"] for item in graded if item["expect"] == "PASS" and not item["passed"]]
    all_attempts = [attempt for item in results for attempt in item["attempts"]]
    first_try_ok = sum(1 for item in results if item["attempts"] and "error" not in item["attempts"][0])
    return {
        "model": model_code,
        "cases": len(results),
        "graded": len(graded),
        "correct": sum(1 for item in graded if item["correct"]),
        "false_approve": false_approve,
        "false_block": false_block,
        "errors": [item["name"] for item in errors],
        "first_attempt_success": first_try_ok,
        "hit_output_limit": sum(1 for a in all_attempts if (a.get("output") or {}).get("hit_output_limit")),
        "normalized_verdicts": [item["name"] for item in graded if item.get("normalized")],
        "model_self_contradictions": [item["name"] for item in graded if item.get("model_contradictions")],
        "avg_seconds_per_call": round(sum(a["seconds"] for a in all_attempts) / max(len(all_attempts), 1), 1),
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="qwen3-8b", help="Mã model đánh giá, ví dụ qwen3-8b, deepseek")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--only", nargs="*", help="Chỉ chạy các case có tên này")
    parser.add_argument("--attempts", type=int, default=2, help="Số lần thử như worker (mặc định 2)")
    parser.add_argument("--out", type=Path, help="Ghi kết quả chi tiết ra file JSON")
    parser.add_argument(
        "--think",
        choices=["on", "off"],
        help="Ghi đè chế độ suy nghĩ của model Ollama (mặc định theo cấu hình model)",
    )
    parser.add_argument("--num-predict", type=int, help="Ghi đè số token output lần chấm đầu")
    args = parser.parse_args()

    data = json.loads(args.cases.read_text(encoding="utf-8"))
    cases = [case for case in data["cases"] if not args.only or case["name"] in args.only]
    model_snapshot = _limit_evaluation_output(
        resolve_direct_model_snapshot(args.model, EVALUATION_CAPABILITY)
    )
    parameters = dict(model_snapshot.get("parameters") or {})
    if args.think:
        parameters["think"] = args.think == "on"
    if args.num_predict:
        parameters["num_predict"] = args.num_predict
    model_snapshot = {**model_snapshot, "parameters": parameters}
    print(f"Model {model_snapshot['model_name']} parameters: {parameters}", flush=True)
    service = QuestionWorkflowService(None)

    results = []
    for index, case in enumerate(cases, start=1):
        result = await _run_case(service, case, data["sources"], model_snapshot, args.attempts)
        results.append(result)
        verdict = "LỖI" if result.get("error") else ("ĐÚNG" if result["correct"] else "SAI")
        print(
            f"[{index}/{len(cases)}] {verdict:4} {case['name']:40} expect={case['expect']:5} "
            f"passed={result['passed']!s:5} action={result.get('action')} "
            f"overall={result.get('overall')} attempts={len(result['attempts'])}",
            flush=True,
        )

    summary = _report(results, args.model)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.out:
        args.out.write_text(
            json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    asyncio.run(main())
