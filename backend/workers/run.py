import asyncio
import logging
import signal

from core.bootstrap import bootstrap_database
from core.database import close_database, get_database, ping_database
from core.job_recovery import recover_stale_jobs
from core.job_worker import run_job_worker
from core.logging import setup_logging
from core.config import settings
from modules.generation.llm.ollama import close_ollama_client
from modules.moodle.publication_worker import MoodlePublicationWorker

logger = logging.getLogger(__name__)


async def run_moodle_worker(stop_event: asyncio.Event) -> None:
    worker = MoodlePublicationWorker(get_database())
    recovered = await asyncio.to_thread(worker.recover_stale)
    if recovered:
        logger.warning("Moved %s stale Moodle publications to UNKNOWN", recovered)
    while not stop_event.is_set():
        result = await asyncio.to_thread(worker.process_next, "moodle-worker")
        if result is None:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=2)
            except asyncio.TimeoutError:
                pass


async def run() -> None:
    setup_logging()
    await asyncio.to_thread(ping_database)
    await asyncio.to_thread(bootstrap_database)
    await asyncio.to_thread(recover_stale_jobs)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stop_event.set)
        except NotImplementedError:
            signal.signal(signum, lambda *_args: loop.call_soon_threadsafe(stop_event.set))

    worker_task = asyncio.gather(
        run_job_worker(stop_event),
        run_moodle_worker(stop_event),
    )
    stop_task = asyncio.create_task(stop_event.wait())
    try:
        done, _pending = await asyncio.wait(
            {worker_task, stop_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if worker_task in done:
            await worker_task
            return
        try:
            await asyncio.wait_for(worker_task, timeout=settings.worker_shutdown_grace_seconds)
        except asyncio.TimeoutError:
            logger.warning("Worker exceeded shutdown grace period; cancelling active work")
            worker_task.cancel()
            await asyncio.gather(worker_task, return_exceptions=True)
    finally:
        stop_task.cancel()
        await close_ollama_client()
        close_database()
        logger.info("Worker database connection closed")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
