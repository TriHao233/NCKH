import asyncio
import logging
import os
import socket
from datetime import datetime, timezone

from core.config import settings
from core.database import get_database

logger = logging.getLogger(__name__)


def get_worker_id() -> str:
    return os.getenv("WORKER_ID", f"{socket.gethostname()}-{os.getpid()}")


async def maintain_lease(heartbeat, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.job_heartbeat_seconds)
        except asyncio.TimeoutError:
            if not await asyncio.to_thread(heartbeat):
                logger.warning("Worker lost its job lease")
                return


def get_next_queued_evaluation_job_id() -> str | None:
    now = datetime.now(timezone.utc)
    doc = get_database().evaluation_jobs.find_one(
        {
            "$or": [
                {
                    "status": "QUEUED",
                    "$or": [
                        {"next_attempt_at": {"$exists": False}},
                        {"next_attempt_at": {"$lte": now}},
                    ],
                },
                {"status": "PROCESSING", "lease_expires_at": {"$lte": now}},
            ]
        },
        sort=[("queued_at", 1)],
        projection={"_id": 1},
    )
    return str(doc["_id"]) if doc else None


async def process_available_jobs_once(worker_id: str | None = None) -> bool:
    """Process at most one job per queue and report whether work was found."""
    from modules.generation.generate import process_generate_background
    from modules.generation.mongodb import get_next_queued_generation_job_id
    from modules.questions.workflow_service import process_evaluation_job_background

    worker_id = worker_id or get_worker_id()
    found_work = False
    generation_job_id = await asyncio.to_thread(get_next_queued_generation_job_id)
    evaluation_job_id = await asyncio.to_thread(get_next_queued_evaluation_job_id)
    tasks = []
    if generation_job_id:
        tasks.append(process_generate_background(generation_job_id, worker_id))
    if evaluation_job_id:
        tasks.append(process_evaluation_job_background(evaluation_job_id, worker_id))
    if tasks:
        found_work = True
        await asyncio.gather(*tasks)
    return found_work


async def run_job_worker(stop_event: asyncio.Event) -> None:
    worker_id = get_worker_id()
    logger.info("Mongo job worker started: %s", worker_id)
    try:
        while not stop_event.is_set():
            try:
                found_work = await process_available_jobs_once(worker_id)
            except Exception:
                logger.exception("Mongo job worker iteration failed")
                found_work = False
            if not found_work:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=settings.job_worker_poll_seconds)
                except asyncio.TimeoutError:
                    pass
    finally:
        logger.info("Mongo job worker stopped")
