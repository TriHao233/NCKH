from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from core.database import get_database
from core.job_worker import maintain_lease
from modules.documents.repository import MongoDocumentRepository

logger = logging.getLogger(__name__)


def get_next_queued_document_job_id() -> str | None:
    now = datetime.now(timezone.utc)
    job = get_database().document_jobs.find_one(
        {
            "job_type": {"$in": ["OCR", "CHUNK", "INDEX"]},
            "$or": [
                {"status": "QUEUED"},
                {"status": "PROCESSING", "lease_expires_at": {"$lte": now}},
            ],
        },
        sort=[("queued_at", 1)],
        projection={"_id": 1},
    )
    return str(job["_id"]) if job else None


async def process_document_job_background(job_id: str, worker_id: str) -> None:
    repository = MongoDocumentRepository(get_database())
    job = await asyncio.to_thread(repository.claim_job, job_id, worker_id)
    if not job:
        return
    fencing_token = int(job.get("fencing_token", 0))
    stop_heartbeat = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        maintain_lease(
            lambda: repository.heartbeat_job(job_id, worker_id, fencing_token),
            stop_heartbeat,
        )
    )
    try:
        config = job.get("config") or {}
        job_type = job.get("job_type")
        await asyncio.to_thread(
            repository.update_checkpoint,
            job_id,
            worker_id,
            fencing_token,
            {"stage": f"{job_type}_STARTED"},
            progress=2,
        )
        if job_type == "OCR":
            await _process_ocr_job(job, config, worker_id, fencing_token)
        elif job_type == "CHUNK":
            await _process_chunk_job(job, config, worker_id, fencing_token)
        elif job_type == "INDEX":
            await _process_index_job(job, config, worker_id, fencing_token)
        else:
            raise ValueError(f"Unsupported document job type: {job_type}")
    except Exception as exc:
        logger.exception("Document job %s failed", job_id)
        failed_job = await asyncio.to_thread(
            repository.update_job,
            job_id,
            "FAILED",
            error_message=str(exc),
            expected_worker_id=worker_id,
            expected_fencing_token=fencing_token,
        )
        if failed_job and job.get("job_type") == "CHUNK":
            now = datetime.now(timezone.utc)
            chunk_set = get_database().chunk_sets.find_one({"chunk_job_id": job["_id"]})
            if chunk_set:
                get_database().chunk_sets.update_one(
                    {"_id": chunk_set["_id"], "status": "PROCESSING"},
                    {
                        "$set": {
                            "status": "FAILED",
                            "error": {"message": str(exc), "at": now},
                            "completed_at": now,
                        }
                    },
                )
                get_database().chunk_embeddings.update_many(
                    {"chunk_set_id": chunk_set["_id"], "status": "PENDING"},
                    {
                        "$set": {
                            "status": "FAILED",
                            "error": {"message": str(exc), "at": now},
                            "updated_at": now,
                        }
                    },
                )
    finally:
        stop_heartbeat.set()
        await heartbeat_task


async def _process_ocr_job(job: dict, config: dict, worker_id: str, fencing_token: int) -> None:
    from modules.ocr.ocr import process_docx_background, process_ocr_background

    required = ("upload_path", "output_path", "document_title")
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise ValueError(f"OCR_JOB_CONFIG_MISSING: {', '.join(missing)}")
    processor = process_docx_background if config.get("source_format") == "docx" else process_ocr_background
    await processor(
        document_id=str(job["document_id"]),
        job_id=str(job["_id"]),
        upload_path=str(config["upload_path"]),
        output_path=str(config["output_path"]),
        document_title=str(config["document_title"]),
        worker_id=worker_id,
        fencing_token=fencing_token,
    )


async def _process_chunk_job(job: dict, config: dict, worker_id: str, fencing_token: int) -> None:
    from modules.rag.chunking import _process_existing_chunk_set

    chunk_set = get_database().chunk_sets.find_one({"chunk_job_id": job["_id"]})
    if not chunk_set:
        raise ValueError("CHUNK_SET_NOT_FOUND")
    await asyncio.to_thread(
        _process_existing_chunk_set,
        str(job["document_id"]),
        str(job["_id"]),
        str(chunk_set["_id"]),
        config,
        worker_id,
        fencing_token,
    )


async def _process_index_job(job: dict, config: dict, worker_id: str, fencing_token: int) -> None:
    from core.config import settings
    from modules.rag.chunking import process_document_reindex_background

    await asyncio.to_thread(
        process_document_reindex_background,
        str(job["document_id"]),
        str(job["_id"]),
        config.get("collection_name") or settings.chromadb_collection_name,
        worker_id,
        fencing_token,
    )
