"""Repeatable local generation benchmark over existing OCR chunk snapshots.

No database writes or cleanup. This measures generation/postprocessing, not OCR,
retrieval quality, or production acceptance. Human grading is exported separately.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import subprocess
import sys
import time
import uuid
from functools import lru_cache

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import settings
from modules.generation.llm.ollama import (
    OllamaProvider,
    close_ollama_client,
    get_ollama_client,
)
from modules.generation.llm.structured_output import extract_question_candidates, parse_structured_json
from modules.generation.mongodb import derive_question_evidence
from modules.generation.postprocessing import POSTPROCESSOR_VERSION, filter_duplicate_questions
from modules.generation.prompt_builder import PromptBuilder
from modules.generation.question import (
    _build_retry_prompt,
    _validate_and_format,
    question_response_schema,
)
from modules.generation.schemas import QuestionType
from modules.rag.search import assess_source_suitability


SELECTION_POLICY_VERSION = "question-source-v3"


def load_prompt_builder(ref: str | None):
    """Load a committed prompt implementation for controlled, read-only comparison."""
    if ref is None:
        return PromptBuilder(), "working-tree"
    root = Path(__file__).resolve().parents[2]
    commit = subprocess.run(
        ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"], cwd=root,
        check=True, capture_output=True, text=True, encoding="utf-8",
    ).stdout.strip()

    @lru_cache(maxsize=None)
    def read_at_commit(path: str) -> str:
        return subprocess.run(
            ["git", "show", f"{commit}:{path}"], cwd=root, check=True,
            capture_output=True, text=True, encoding="utf-8",
        ).stdout

    # Execute only this repository's explicitly selected, locally reviewed builder.
    namespace = {"__name__": "benchmark_committed_prompt_builder"}
    body = read_at_commit("backend/modules/generation/prompt_builder.py")
    exec(compile(body, f"{commit}:prompt_builder.py", "exec"), namespace)
    builder_class = namespace["PromptBuilder"]

    def load_template(key: str, relative_path: str):
        text = read_at_commit(f"backend/prompts/{relative_path}")
        return text, {"template_key": key, "source": "git", "version": commit,
                      "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                      "relative_path": relative_path}

    builder_class._load_template = staticmethod(load_template)
    return builder_class(), commit


def load_snapshots(paths: list[Path]) -> list[dict]:
    snapshots = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        chunks = [item for item in payload.get("chunks", []) if item.get("content") and item.get("chunk_id")]
        if not chunks:
            raise ValueError(f"No source chunks in {path}")
        snapshots.append({
            "path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "document_id": payload.get("document_id"), "chunks": chunks,
        })
    return snapshots


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(ordered[rank], 3)


def summarize(
    records: list[dict],
    *,
    reviews: list[dict] | None = None,
    review_key: list[dict] | None = None,
    source_reviews: list[dict] | None = None,
) -> dict:
    usable_records: set[int] = set()
    graded_records: set[int] = set()
    graded_accepted_records: set[int] = set()
    if reviews is not None and review_key is not None:
        review_by_id = {item["blind_id"]: item for item in reviews}
        for key in review_key:
            review = review_by_id.get(key["blind_id"])
            if not review:
                continue
            grading = review.get("grading") or {}
            record_index = int(key["record_index"])
            if grading.get("usable_without_edit") is not None:
                graded_records.add(record_index)
                if key.get("technically_accepted"):
                    graded_accepted_records.add(record_index)
            if key.get("technically_accepted") and grading.get("usable_without_edit") is True:
                usable_records.add(record_index)

    source_grade_by_id = {
        item["source_review_id"]: item.get("grading") or {}
        for item in (source_reviews or [])
    }
    groups = {}
    for record_index, record in enumerate(records):
        key = f"{record['model']}/{record['question_type']}"
        group = groups.setdefault(key, {
            "requested": 0,
            "model_calls": 0,
            "candidate_count": 0,
            "accepted_requests": 0,
            "accepted_candidates": 0,
            "retry_requests": 0,
            "source_refusals": 0,
            "source_refusal_correct": 0,
            "source_refusal_incorrect": 0,
            "elapsed_values": [],
            "usable_requests": 0,
            "graded_requests": 0,
            "graded_accepted_requests": 0,
            "rejections": Counter(),
        })
        group["requested"] += 1
        group["model_calls"] += len(record["attempts"])
        group["candidate_count"] += sum(
            int(attempt.get("candidate_count") or 0) for attempt in record["attempts"]
        )
        group["accepted_requests"] += bool(record["accepted"])
        group["accepted_candidates"] += len(record["accepted"])
        group["retry_requests"] += len(record["attempts"]) > 1
        group["source_refusals"] += record.get("source_status") == "insufficient"
        group["elapsed_values"].append(float(record["elapsed_seconds"]))
        group["usable_requests"] += record_index in usable_records
        group["graded_requests"] += record_index in graded_records
        group["graded_accepted_requests"] += record_index in graded_accepted_records
        source_grade = source_grade_by_id.get(record.get("source_review_id"), {})
        if record.get("source_status") == "insufficient":
            group["source_refusal_correct"] += source_grade.get("refusal_correct") is True
            group["source_refusal_incorrect"] += source_grade.get("refusal_correct") is False
        for attempt in record["attempts"]:
            group["rejections"].update(item["code"] for item in attempt["rejections"])
    for group in groups.values():
        requested = group["requested"]
        accepted = group["accepted_requests"]
        usable = group["usable_requests"]
        graded_accepted = group["graded_accepted_requests"]
        elapsed = group.pop("elapsed_values")
        total_elapsed = round(sum(elapsed), 3)
        group.update({
            "technical_pass_rate": round(accepted / requested, 4) if requested else None,
            "accepted_quality_rate": round(usable / graded_accepted, 4) if graded_accepted else None,
            "retry_rate": round(group["retry_requests"] / requested, 4) if requested else None,
            "elapsed_seconds_total": total_elapsed,
            "latency_seconds_median": round(statistics.median(elapsed), 3) if elapsed else None,
            "latency_seconds_p95": _percentile(elapsed, 0.95),
            "seconds_per_usable_request": round(total_elapsed / usable, 3) if usable else None,
        })
    return {
        "scope": "fixed OCR snapshots; deterministic type-aware source selection, generation and postprocessing",
        "human_graded": bool(graded_records),
        "metric_notes": {
            "accepted_requests": "requests with at least one candidate accepted by validators",
            "usable_requests": "technically accepted requests with at least one blind-reviewed usable candidate",
            "accepted_quality_rate": "usable accepted requests divided by reviewed accepted requests; null until an accepted request is reviewed",
            "seconds_per_usable_request": "all request time including retries/refusals divided by usable requests; null when none",
        },
        "groups": groups,
    }


def select_benchmark_chunks(
    chunks: list[dict],
    question_type: str,
    *,
    start: int,
    search_limit: int,
    selected_limit: int,
) -> tuple[list[dict], dict]:
    """Select a reproducible, bounded set of individually suitable chunks."""
    examined = []
    selected = []
    for offset in range(min(len(chunks), search_limit)):
        item = chunks[(start + offset) % len(chunks)]
        assessment = assess_source_suitability(item.get("content") or "", question_type)
        examined.append({"chunk_id": item.get("chunk_id"), **assessment})
        if assessment["suitable"]:
            selected.append(item)
            if len(selected) >= selected_limit:
                break
    rejection_counts = Counter(
        reason
        for assessment in examined
        if not assessment["suitable"]
        for reason in assessment["reasons"]
    )
    return selected, {
        "policy_version": SELECTION_POLICY_VERSION,
        "question_type": question_type,
        "start": start,
        "search_limit": search_limit,
        "selected_limit": selected_limit,
        "examined_count": len(examined),
        "eligible_count": sum(item["suitable"] for item in examined),
        "status": "selected" if selected else "insufficient",
        "rejection_reasons": rejection_counts,
        "assessments": examined,
    }


def validator_manifest() -> dict:
    root = Path(__file__).resolve().parents[1]
    return {"version": POSTPROCESSOR_VERSION, "file_hashes": {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in (
            "modules/generation/postprocessing.py", "modules/generation/question.py",
            "modules/generation/mongodb.py", "modules/questions/contracts.py",
            "modules/rag/search.py", "scripts/benchmark_questions_local.py",
        )
    }}


def repository_snapshot() -> dict:
    root = Path(__file__).resolve().parents[2]
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        capture_output=True, text=True, encoding="utf-8",
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--short"], cwd=root, check=True,
        capture_output=True, text=True, encoding="utf-8",
    ).stdout
    return {"head": head, "working_tree_dirty": bool(status.strip())}


async def ollama_model_manifest(generate_url: str, model: str, timeout: float) -> dict:
    base_url = generate_url.rsplit("/api/generate", 1)[0]
    show_url = base_url + "/api/show"
    try:
        response = await get_ollama_client().post(
            show_url,
            json={"model": model},
            timeout=min(timeout, 30),
        )
        response.raise_for_status()
        payload = response.json()
        tags_response = await get_ollama_client().get(
            base_url + "/api/tags",
            timeout=min(timeout, 30),
        )
        tags_response.raise_for_status()
        tag = next(
            (
                item
                for item in tags_response.json().get("models") or []
                if item.get("name") == model or item.get("model") == model
            ),
            {},
        )
        return {
            "model": model,
            "digest": tag.get("digest"),
            "modified_at": payload.get("modified_at"),
            "details": payload.get("details") or {},
            "model_info": payload.get("model_info") or {},
            "template_sha256": hashlib.sha256(
                str(payload.get("template") or "").encode("utf-8")
            ).hexdigest(),
            "modelfile_sha256": hashlib.sha256(
                str(payload.get("modelfile") or "").encode("utf-8")
            ).hexdigest(),
        }
    except Exception as exc:
        return {"model": model, "metadata_unavailable": str(exc)}


def write_run_progress(output: Path, records: list[dict]) -> None:
    with (output / "results.jsonl").open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    (output / "summary.json").write_text(
        json.dumps(summarize(records), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def replay(args) -> None:
    """Recheck saved responses without spending inference time or changing originals."""
    records = [json.loads(line) for line in args.replay.read_text(encoding="utf-8").splitlines() if line.strip()]
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    for record_index, record in enumerate(records):
        for attempt_index, attempt in enumerate(record["attempts"]):
            try:
                candidates = extract_question_candidates(parse_structured_json(attempt["raw_response"]))
                valid, errors = _validate_and_format(
                    candidates, question_type=record["question_type"], bloom_level="2_hieu",
                    context_text="\n\n".join(item["content"] for item in record["chunks"]), allowed_clo_codes=[],
                )
                reasons = [error.model_dump() for error in errors]
                accepted = []
                for item in valid:
                    try:
                        item.evidence_spans = derive_question_evidence(item.model_dump(), record["chunks"])
                        accepted.append(item.model_dump())
                    except ValueError as exc:
                        reasons.append({"code": "QUESTION_EVIDENCE_INVALID", "message": str(exc)})
            except ValueError as exc:
                accepted, reasons = [], [{"code": "GENERATION_FAILED", "message": str(exc)}]
            rows.append({"record_index": record_index, "attempt_index": attempt_index,
                         "question_type": record["question_type"], "model": record["model"],
                         "accepted": accepted, "rejections": reasons})
    report = {"scope": "saved candidate revalidation; no new inference or human grading",
              "source": str(args.replay.resolve()), "source_sha256": hashlib.sha256(args.replay.read_bytes()).hexdigest(),
              "validator": validator_manifest(), "attempts": rows}
    (args.output / "revalidation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"attempts": len(rows), "accepted_candidates": sum(len(row["accepted"]) for row in rows)}, indent=2))


def summarize_reviewed_run(run_dir: Path) -> None:
    """Merge completed blind/source grading without changing raw benchmark evidence."""
    records = [
        json.loads(line)
        for line in (run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    reviews = json.loads((run_dir / "blind-review.json").read_text(encoding="utf-8"))
    review_key = json.loads((run_dir / "review-key.json").read_text(encoding="utf-8"))
    source_review_path = run_dir / "source-review.json"
    source_reviews = (
        json.loads(source_review_path.read_text(encoding="utf-8"))
        if source_review_path.exists()
        else []
    )
    report = summarize(
        records,
        reviews=reviews,
        review_key=review_key,
        source_reviews=source_reviews,
    )
    report["review_inputs"] = {
        name: hashlib.sha256((run_dir / name).read_bytes()).hexdigest()
        for name in ("results.jsonl", "blind-review.json", "review-key.json")
    }
    if source_review_path.exists():
        report["review_inputs"]["source-review.json"] = hashlib.sha256(
            source_review_path.read_bytes()
        ).hexdigest()
    destination = run_dir / "reviewed-summary.json"
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"reviewed_summary": str(destination.resolve())}, ensure_ascii=False, indent=2))


async def run(args) -> None:
    if settings.prompt_source != "file":
        raise ValueError("Set PROMPT_SOURCE=file to benchmark the checked-out prompt files.")
    snapshots = load_snapshots(args.snapshots)
    prompt_builder, prompt_source = load_prompt_builder(args.prompt_ref)
    model_manifests = [
        await ollama_model_manifest(args.url, model, args.timeout)
        for model in args.models
    ]
    # Exclusive directory creation prevents accidental replacement of earlier evidence.
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "validator_version": POSTPROCESSOR_VERSION, "models": args.models,
        "model_manifests": model_manifests,
        "prompt_source": prompt_source,
        "validator": validator_manifest(),
        "repository": repository_snapshot(),
        "samples_per_type_per_model": args.samples, "types": args.types,
        "parameters": {
            "temperature": args.temperature,
            "num_ctx": args.num_ctx,
            "num_predict": args.num_predict,
            "max_retries": args.retries,
            "timeout_seconds": args.timeout,
            "ollama_url": args.url,
            "structured_schema": args.structured_schema,
        },
        "source_selection": {
            "policy_version": SELECTION_POLICY_VERSION,
            "chunk_start": args.chunk_start,
            "search_limit": args.source_search_limit,
            "selected_limit": args.context_chunks,
        },
        "snapshots": [{key: value for key, value in item.items() if key != "chunks"} for item in snapshots],
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    records, blind, answer_key, source_reviews = [], [], [], []
    source_review_ids = {}
    try:
        for model in args.models:
            provider = OllamaProvider(
                model,
                url=args.url,
                timeout_seconds=args.timeout,
                num_ctx=args.num_ctx,
                num_predict=args.num_predict,
                temperature=args.temperature,
            )
            for kind in args.types:
                seen, avoid = set(), []
                for sample_index in range(args.samples):
                    request_started = time.perf_counter()
                    snapshot = snapshots[sample_index % len(snapshots)]
                    chunks = snapshot["chunks"]
                    # Same deterministic search and suitability policy for every model.
                    start = (sample_index * args.context_chunks + args.chunk_start) % len(chunks)
                    selected, selection = select_benchmark_chunks(
                        chunks,
                        kind,
                        start=start,
                        search_limit=args.source_search_limit,
                        selected_limit=args.context_chunks,
                    )
                    source_key = (snapshot["sha256"], kind, sample_index, start)
                    source_review_id = source_review_ids.get(source_key)
                    if source_review_id is None:
                        source_review_id = uuid.uuid4().hex
                        source_review_ids[source_key] = source_review_id
                        source_reviews.append({
                            "source_review_id": source_review_id,
                            "snapshot_sha256": snapshot["sha256"],
                            "question_type": kind,
                            "sample_index": sample_index,
                            "automatic_status": selection["status"],
                            "selected_chunk_ids": [item["chunk_id"] for item in selected],
                            "examined": selection["assessments"],
                            "grading": {
                                "eligible_for_type": None,
                                "refusal_correct": None,
                                "comments": "",
                            },
                        })
                    record = {
                        "model": model,
                        "question_type": kind,
                        "sample_index": sample_index,
                        "snapshot_sha256": snapshot["sha256"],
                        "chunks": selected,
                        "source_review_id": source_review_id,
                        "source_status": selection["status"],
                        "source_selection": selection,
                        "attempts": [],
                        "accepted": [],
                    }
                    if not selected:
                        record["elapsed_seconds"] = round(
                            time.perf_counter() - request_started,
                            3,
                        )
                        records.append(record)
                        write_run_progress(args.output, records)
                        print(
                            f"{model} {kind} {sample_index + 1}/{args.samples}: "
                            "source refused before inference",
                            flush=True,
                        )
                        continue
                    context = "\n\n".join(f"Mục lục: [{item.get('metadata', {}).get('heading', '')}]\nNội dung: {item['content']}" for item in selected)
                    built = prompt_builder.build_with_manifest(context, "2_hieu", kind, 1, avoid_questions=avoid)
                    prompt = built["rendered_prompt"]
                    record.update({
                        "prompt_release_hash": built["release_hash"],
                        "rendered_prompt_hash": built["rendered_prompt_hash"],
                        "prompt_templates": built["templates"],
                    })
                    blind_candidates = []
                    for attempt_no in range(args.retries + 1):
                        attempt = {
                            "attempt_no": attempt_no + 1,
                            "prompt": prompt,
                            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                            "raw_response": "",
                            "candidate_count": 0,
                            "rejections": [],
                        }
                        candidates = []
                        try:
                            response_schema = (
                                question_response_schema(kind, "2_hieu", 1)
                                if args.structured_schema else None
                            )
                            attempt["raw_response"] = await provider.generate_text(
                                prompt, response_schema=response_schema,
                            )
                            candidates = extract_question_candidates(parse_structured_json(attempt["raw_response"]))
                            attempt["candidate_count"] = len(candidates)
                            valid, errors = _validate_and_format(candidates, question_type=kind, bloom_level="2_hieu", context_text=context, allowed_clo_codes=[])
                            attempt["rejections"] = [error.model_dump() for error in errors]
                            grounded = []
                            for item in valid:
                                try:
                                    item.evidence_spans = derive_question_evidence(item.model_dump(), selected)
                                    grounded.append(item)
                                except ValueError as exc:
                                    attempt["rejections"].append({"code": "QUESTION_EVIDENCE_INVALID", "message": str(exc)})
                            kept, duplicates = filter_duplicate_questions(grounded, seen, limit=1)
                            if duplicates.total:
                                attempt["rejections"].append({"code": "DUPLICATE_QUESTION", "message": "Repeated question in this model/type cell"})
                            record["accepted"] = [item.model_dump() for item in kept]
                        except (RuntimeError, ValueError) as exc:
                            attempt["rejections"].append({"code": "GENERATION_FAILED", "message": str(exc)})
                        blind_candidates.extend(
                            {
                                "attempt_no": attempt_no + 1,
                                "candidate_index": candidate_index,
                                "question": json.loads(json.dumps(item, ensure_ascii=False)),
                            }
                            for candidate_index, item in enumerate(candidates)
                            if isinstance(item, dict)
                        )
                        record["attempts"].append(attempt)
                        if record["accepted"] or attempt_no == args.retries:
                            break
                        prompt = _build_retry_prompt(original_prompt=built["rendered_prompt"], question_type=kind,
                                                     bloom_level="2_hieu", missing_count=1,
                                                     validation_errors=attempt["rejections"], avoid_questions=avoid)
                    # Review every parsed candidate, including rejected candidates from
                    # earlier attempts, so false validator rejections remain measurable.
                    for blind_candidate in blind_candidates:
                        item = blind_candidate["question"]
                        blind_id = uuid.uuid4().hex
                        blind.append({
                            "blind_id": blind_id,
                            "requested_type": kind,
                            "question": {
                                key: item.get(key)
                                for key in (
                                    "question",
                                    "options",
                                    "correct_answer",
                                    "explanation",
                                    "source_context",
                                )
                            },
                            "reference_context": context,
                            "grading": {
                                "factually_correct": None,
                                "correct_type": None,
                                "usable_without_edit": None,
                                "comments": "",
                            },
                        })
                        answer_key.append({
                            "blind_id": blind_id,
                            "model": model,
                            "record_index": len(records),
                            "attempt_no": blind_candidate["attempt_no"],
                            "candidate_index": blind_candidate["candidate_index"],
                            "technically_accepted": any(
                                accepted.get("question") == item.get("question")
                                and accepted.get("correct_answer") == item.get("correct_answer")
                                and accepted.get("source_context") == item.get("source_context")
                                for accepted in record["accepted"]
                            ),
                        })
                    record["elapsed_seconds"] = round(
                        time.perf_counter() - request_started,
                        3,
                    )
                    records.append(record)
                    avoid.extend(item["question"] for item in record["accepted"])
                    write_run_progress(args.output, records)
                    print(f"{model} {kind} {sample_index + 1}/{args.samples}: accepted={len(record['accepted'])}, {record['elapsed_seconds']}s", flush=True)
    finally:
        random.Random(20260908).shuffle(blind)
        (args.output / "blind-review.json").write_text(json.dumps(blind, ensure_ascii=False, indent=2), encoding="utf-8")
        (args.output / "review-key.json").write_text(json.dumps(answer_key, ensure_ascii=False, indent=2), encoding="utf-8")
        (args.output / "source-review.json").write_text(
            json.dumps(source_reviews, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        await close_ollama_client()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshots", type=Path, nargs="+", default=[])
    parser.add_argument("--replay", type=Path, help="Revalidate a saved results.jsonl without calling a model")
    parser.add_argument("--summarize-run", type=Path, help="Merge completed blind grading into reviewed-summary.json")
    parser.add_argument("--prompt-ref", help="Git revision for baseline prompts; transport, validators and retry policy stay current")
    parser.add_argument("--output", type=Path, help="New directory for results and blind review")
    parser.add_argument("--models", nargs="+", default=["ornith:latest", "qwen2.5:7b", "deepseek-r1:latest"])
    parser.add_argument("--types", nargs="+", choices=[item.value for item in QuestionType], default=[item.value for item in QuestionType])
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--chunk-start", type=int, default=0)
    parser.add_argument("--source-search-limit", type=int, default=24)
    parser.add_argument("--context-chunks", type=int, default=3)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--num-ctx", type=int, default=8192)
    parser.add_argument("--num-predict", type=int, default=2048)
    parser.add_argument("--temperature", type=float, default=0)
    parser.add_argument(
        "--structured-schema", action="store_true",
        help="Ask Ollama to enforce the type-specific JSON schema during decoding",
    )
    parser.add_argument("--url", default="http://localhost:11434/api/generate")
    parser.add_argument("--timeout", type=float, default=300)
    args = parser.parse_args()
    if args.summarize_run:
        summarize_reviewed_run(args.summarize_run)
        return
    if not args.output:
        parser.error("--output is required for benchmark and replay modes")
    if args.replay:
        replay(args)
        return
    if args.samples < 1:
        parser.error("--samples must be positive")
    if args.source_search_limit < 1 or args.context_chunks < 1:
        parser.error("--source-search-limit and --context-chunks must be positive")
    if args.retries < 0 or args.retries > 3:
        parser.error("--retries must be between 0 and 3")
    if not args.snapshots:
        parser.error("--snapshots is required unless --replay is supplied")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
