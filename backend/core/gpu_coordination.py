"""Small cross-process GPU operation lock shared by backend and worker."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from core.config import resolve_path, settings

logger = logging.getLogger(__name__)


def _lock_path() -> Path:
    configured = Path(settings.gpu_lock_path)
    return configured if configured.is_absolute() else resolve_path(configured)


def _remove_stale_lock(path: Path) -> None:
    try:
        age_seconds = time.time() - path.stat().st_mtime
    except FileNotFoundError:
        return
    if age_seconds <= settings.gpu_lock_stale_seconds:
        return
    try:
        path.unlink()
        logger.warning("Removed stale GPU lock at %s after %.1f seconds", path, age_seconds)
    except FileNotFoundError:
        pass


@contextmanager
def gpu_operation(label: str) -> Iterator[None]:
    """Serialize long GPU operations across processes sharing ``GPU_LOCK_PATH``."""

    if not settings.gpu_coordination_enabled:
        yield
        return

    path = _lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    payload = json.dumps(
        {
            "token": token,
            "pid": os.getpid(),
            "label": label,
            "created_at": time.time(),
        },
        separators=(",", ":"),
    ).encode("utf-8")
    deadline = time.monotonic() + settings.gpu_lock_timeout_seconds

    while True:
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            _remove_stale_lock(path)
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for GPU operation slot: {label}")
            time.sleep(max(settings.gpu_lock_poll_seconds, 0.05))
            continue
        try:
            os.write(descriptor, payload)
        finally:
            os.close(descriptor)
        break

    try:
        yield
    finally:
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            current = {}
        if current.get("token") == token:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
