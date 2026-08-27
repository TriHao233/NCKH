import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from core.config import settings
from core.database import get_database
from modules.generation.llm.base import LLMProvider

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def provider_concurrency_group(provider_code: str) -> str:
    normalized = provider_code.strip().lower()
    if normalized == "gemini":
        return "gemini"
    if normalized in {"qwen", "deepseek", "deepseek-r1", "deepseek-r1:8b"} or normalized.startswith(
        "ollama:"
    ):
        return "ollama"
    return f"provider:{normalized}"


def provider_concurrency_limit(group: str) -> int:
    if group == "gemini":
        configured = settings.gemini_max_concurrency
    elif group == "ollama":
        configured = settings.ollama_max_concurrency
    else:
        configured = 1
    return max(1, configured)


def _ensure_slots(group: str, limit: int) -> None:
    collection = get_database().llm_slots
    now = utc_now()
    for slot_index in range(limit):
        try:
            collection.update_one(
                {"_id": f"{group}:{slot_index}"},
                {
                    "$setOnInsert": {
                        "provider": group,
                        "slot_index": slot_index,
                        "holder_id": None,
                        "lease_expires_at": None,
                        "updated_at": now,
                    }
                },
                upsert=True,
            )
        except DuplicateKeyError:
            # Another worker created this fixed slot between our read and upsert.
            continue


def _try_acquire_slot(group: str, holder_id: str, limit: int) -> str | None:
    _ensure_slots(group, limit)
    now = utc_now()
    slot = get_database().llm_slots.find_one_and_update(
        {
            "provider": group,
            "slot_index": {"$lt": limit},
            "$or": [
                {"holder_id": None},
                {"holder_id": {"$exists": False}},
                {"lease_expires_at": {"$lte": now}},
                {"holder_id": holder_id},
            ],
        },
        {
            "$set": {
                "holder_id": holder_id,
                "lease_expires_at": now + timedelta(seconds=settings.llm_slot_lease_seconds),
                "updated_at": now,
            }
        },
        sort=[("slot_index", 1)],
        return_document=ReturnDocument.AFTER,
    )
    return str(slot["_id"]) if slot else None


def _heartbeat_slot(slot_id: str, holder_id: str) -> bool:
    now = utc_now()
    result = get_database().llm_slots.update_one(
        {"_id": slot_id, "holder_id": holder_id},
        {
            "$set": {
                "lease_expires_at": now + timedelta(seconds=settings.llm_slot_lease_seconds),
                "updated_at": now,
            }
        },
    )
    return result.matched_count == 1


def _release_slot(slot_id: str, holder_id: str) -> None:
    get_database().llm_slots.update_one(
        {"_id": slot_id, "holder_id": holder_id},
        {
            "$set": {
                "holder_id": None,
                "lease_expires_at": None,
                "updated_at": utc_now(),
            }
        },
    )


async def _maintain_slot(slot_id: str, holder_id: str, stop_event: asyncio.Event) -> None:
    interval = max(1, settings.llm_slot_heartbeat_seconds)
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            if not await asyncio.to_thread(_heartbeat_slot, slot_id, holder_id):
                logger.warning("LLM slot %s is no longer owned by %s", slot_id, holder_id)
                return


@asynccontextmanager
async def distributed_llm_slot(provider_code: str):
    group = provider_concurrency_group(provider_code)
    limit = provider_concurrency_limit(group)
    holder_id = uuid4().hex
    deadline = asyncio.get_running_loop().time() + settings.llm_slot_wait_timeout_seconds
    slot_id = None

    while slot_id is None:
        slot_id = await asyncio.to_thread(_try_acquire_slot, group, holder_id, limit)
        if slot_id is not None:
            break
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError(f"Hết thời gian chờ tài nguyên LLM provider {group}")
        await asyncio.sleep(max(0.05, settings.llm_slot_poll_seconds))

    stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(_maintain_slot(slot_id, holder_id, stop_event))
    try:
        yield slot_id
    finally:
        stop_event.set()
        await heartbeat_task
        await asyncio.to_thread(_release_slot, slot_id, holder_id)


class ConcurrencyLimitedProvider(LLMProvider):
    def __init__(self, provider_code: str, wrapped: LLMProvider):
        self.provider_code = provider_code
        self.wrapped = wrapped

    def __getattr__(self, name: str):
        return getattr(self.wrapped, name)

    async def generate_text(self, prompt: str) -> str:
        async with distributed_llm_slot(self.provider_code):
            return await self.wrapped.generate_text(prompt)
