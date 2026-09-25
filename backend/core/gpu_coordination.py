"""Small cross-process GPU operation lease shared by backend and worker."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import threading
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import AsyncIterator, Iterator

from core.config import resolve_path, settings

logger = logging.getLogger(__name__)


def _lock_path() -> Path:
    configured = Path(settings.gpu_lock_path)
    return configured if configured.is_absolute() else resolve_path(configured)


def current_gpu_operation_label() -> str | None:
    """Return the current GPU lease label without waiting for the lease."""
    label = _read_lock(_lock_path()).get("label")
    return str(label) if label else None


def _read_lock(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def _remove_stale_lock(path: Path) -> bool:
    try:
        first_mtime = path.stat().st_mtime
    except FileNotFoundError:
        return False
    age_seconds = time.time() - first_mtime
    if age_seconds <= settings.gpu_lock_stale_seconds:
        return False

    owner = _read_lock(path)
    try:
        # A heartbeat between the first stat and this check means the owner is alive.
        if path.stat().st_mtime != first_mtime:
            return False
        path.unlink()
        logger.warning(
            "Removed stale GPU lock label=%s host=%s pid=%s after %.1f seconds",
            owner.get("label"),
            owner.get("hostname"),
            owner.get("pid"),
            age_seconds,
        )
        return True
    except FileNotFoundError:
        return False


def _try_acquire(path: Path, *, token: str, label: str) -> bool:
    payload = json.dumps(
        {
            "token": token,
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "label": label,
            "created_at": time.time(),
        },
        separators=(",", ":"),
    ).encode("utf-8")
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    try:
        os.write(descriptor, payload)
    except Exception:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise
    finally:
        os.close(descriptor)
    return True


def _heartbeat(path: Path, token: str, stop: threading.Event) -> None:
    interval = max(float(settings.gpu_lock_heartbeat_seconds), 0.1)
    while not stop.wait(interval):
        if _read_lock(path).get("token") != token:
            return
        try:
            os.utime(path, None)
        except FileNotFoundError:
            return
        except OSError as exc:
            logger.warning("Could not refresh GPU lock heartbeat at %s: %s", path, exc)


def _start_heartbeat(path: Path, token: str) -> tuple[threading.Event, threading.Thread]:
    stop = threading.Event()
    thread = threading.Thread(
        target=_heartbeat,
        args=(path, token, stop),
        name="gpu-lock-heartbeat",
        daemon=True,
    )
    thread.start()
    return stop, thread


def _release_lock(
    path: Path,
    token: str,
    stop: threading.Event,
    heartbeat_thread: threading.Thread,
) -> None:
    stop.set()
    heartbeat_thread.join(timeout=1.0)
    if _read_lock(path).get("token") != token:
        return
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _timeout_error(label: str) -> TimeoutError:
    owner = _read_lock(_lock_path())
    owner_label = owner.get("label") or "unknown"
    owner_host = owner.get("hostname") or "legacy-container"
    return TimeoutError(
        f"Timed out waiting for GPU operation slot: {label} "
        f"(held by {owner_label} on {owner_host})"
    )


@contextmanager
def gpu_operation(label: str) -> Iterator[None]:
    """Serialize GPU work and reclaim a lease when its heartbeat stops."""
    if not settings.gpu_coordination_enabled:
        yield
        return

    path = _lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    deadline = time.monotonic() + settings.gpu_lock_timeout_seconds

    while not _try_acquire(path, token=token, label=label):
        _remove_stale_lock(path)
        if time.monotonic() >= deadline:
            raise _timeout_error(label)
        time.sleep(max(settings.gpu_lock_poll_seconds, 0.05))

    stop, heartbeat_thread = _start_heartbeat(path, token)
    try:
        yield
    finally:
        _release_lock(path, token, stop, heartbeat_thread)


@asynccontextmanager
async def async_gpu_operation(label: str) -> AsyncIterator[None]:
    """Cancellation-safe async GPU lease acquisition without a background waiter."""
    if not settings.gpu_coordination_enabled:
        yield
        return

    path = _lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    deadline = time.monotonic() + settings.gpu_lock_timeout_seconds

    while not _try_acquire(path, token=token, label=label):
        _remove_stale_lock(path)
        if time.monotonic() >= deadline:
            raise _timeout_error(label)
        await asyncio.sleep(max(settings.gpu_lock_poll_seconds, 0.05))

    stop, heartbeat_thread = _start_heartbeat(path, token)
    try:
        yield
    finally:
        _release_lock(path, token, stop, heartbeat_thread)
