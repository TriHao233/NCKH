import asyncio
import logging

from core.config import settings
from core.database import get_database

logger = logging.getLogger(__name__)


def get_next_queued_evaluation_job_id() -> str | None:
    doc = get_database().evaluation_jobs.find_one(
        {"status": "QUEUED"},
        sort=[("queued_at", 1)],
        projection={"_id": 1},
    )
    return str(doc["_id"]) if doc else None


async def process_available_jobs_once() -> bool:
    """Process at most one job per queue and report whether work was found."""
    from modules.generation.generate import process_generate_background
    from modules.generation.mongodb import get_next_queued_generation_job_id
    from modules.questions.workflow_service import process_evaluation_job_background

    found_work = False
    generation_job_id = await asyncio.to_thread(get_next_queued_generation_job_id)
    evaluation_job_id = await asyncio.to_thread(get_next_queued_evaluation_job_id)
    tasks = []
    if generation_job_id:
        tasks.append(process_generate_background(generation_job_id))
    if evaluation_job_id:
        tasks.append(process_evaluation_job_background(evaluation_job_id))
    if tasks:
        found_work = True
        await asyncio.gather(*tasks)
    return found_work


async def run_job_worker(stop_event: asyncio.Event) -> None:
    logger.info("Mongo job worker started")
    try:
        while not stop_event.is_set():
            try:
                found_work = await process_available_jobs_once()
            except Exception:
                logger.exception("Mongo job worker iteration failed")
                found_work = False
            if not found_work:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=settings.job_worker_poll_seconds)
                except TimeoutError:
                    pass
    finally:
        logger.info("Mongo job worker stopped")
