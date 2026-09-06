"""Seed, age, and verify a real OCR worker crash/restart acceptance drill."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bson import ObjectId

from core.database import close_database, get_database
from modules.documents.repository import MongoDocumentRepository
from modules.documents.schemas import DocumentCreateRequest


def _json(value: dict) -> None:
    print(json.dumps(value, default=str, ensure_ascii=False))


def seed(upload_path: Path, output_path: Path) -> dict:
    db = get_database()
    repository = MongoDocumentRepository(db)
    raw = upload_path.read_bytes()
    document = repository.create(
        DocumentCreateRequest(
            title="OCR crash acceptance",
            original_filename=upload_path.name,
            original_uri=str(upload_path),
            size_bytes=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
        ).model_dump(),
        ObjectId(),
    )
    job = repository.create_job(
        document["_id"],
        "OCR",
        {
            "upload_path": str(upload_path),
            "output_path": str(output_path),
            "document_title": document["title"],
            "source_format": "pdf",
        },
    )
    return {"document_id": str(document["_id"]), "job_id": str(job["_id"])}


def age(job_id: str) -> dict:
    db = get_database()
    old = datetime.now(timezone.utc) - timedelta(minutes=5)
    job = db.document_jobs.find_one_and_update(
        {"_id": ObjectId(job_id), "status": "PROCESSING"},
        {
            "$set": {
                "updated_at": old,
                "heartbeat_at": old,
                "lease_expires_at": old,
            }
        },
        return_document=True,
    )
    if not job:
        raise RuntimeError("Job is not PROCESSING; the worker was not interrupted in-flight")
    return {"job_id": job_id, "status": job["status"], "aged_at": old.isoformat()}


def status(job_id: str) -> dict:
    db = get_database()
    job = db.document_jobs.find_one({"_id": ObjectId(job_id)})
    if not job:
        raise RuntimeError("Job not found")
    return {
        "job_id": job_id,
        "status": job.get("status"),
        "progress": job.get("progress"),
        "worker_id": job.get("worker_id"),
        "fencing_token": job.get("fencing_token"),
        "run_attempt": job.get("run_attempt"),
        "checkpoint": job.get("checkpoint"),
        "updated_at": job.get("updated_at"),
        "error": job.get("error"),
    }


def verify(job_id: str, document_id: str) -> dict:
    db = get_database()
    job = db.document_jobs.find_one({"_id": ObjectId(job_id)})
    document = db.documents.find_one({"_id": ObjectId(document_id)})
    pages = list(
        db.document_pages.find(
            {
                "document_id": ObjectId(document_id),
                "ocr_job_id": ObjectId(job_id),
            }
        ).sort("page_number", 1)
    )
    page_numbers = [int(page["page_number"]) for page in pages]
    checks = {
        "job_completed": (job or {}).get("status") == "COMPLETED",
        "retried_after_crash": int((job or {}).get("run_attempt") or 0) >= 2,
        "fencing_advanced": int((job or {}).get("fencing_token") or 0) >= 2,
        "document_ready_for_next_stage": (document or {}).get("pipeline_summary", {}).get("ocr_status")
        == "COMPLETED",
        "pages_persisted": bool(pages),
        "page_numbers_unique": len(page_numbers) == len(set(page_numbers)),
        "page_numbers_contiguous": page_numbers == list(range(1, len(page_numbers) + 1)),
        "page_count_matches_document": len(pages) == int((document or {}).get("page_count") or 0),
    }
    return {
        "job_id": job_id,
        "document_id": document_id,
        "checks": checks,
        "passed": all(checks.values()),
        "job": status(job_id),
        "page_count": len(pages),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    seed_parser = subparsers.add_parser("seed")
    seed_parser.add_argument("--upload", type=Path, required=True)
    seed_parser.add_argument("--output", type=Path, required=True)
    age_parser = subparsers.add_parser("age")
    age_parser.add_argument("--job-id", required=True)
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--job-id", required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--job-id", required=True)
    verify_parser.add_argument("--document-id", required=True)
    args = parser.parse_args()
    try:
        if args.command == "seed":
            result = seed(args.upload.resolve(), args.output.resolve())
        elif args.command == "age":
            result = age(args.job_id)
        elif args.command == "status":
            result = status(args.job_id)
        else:
            result = verify(args.job_id, args.document_id)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                json.dumps(result, default=str, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        _json(result)
        return 0 if result.get("passed", True) else 2
    finally:
        close_database()


if __name__ == "__main__":
    raise SystemExit(main())
