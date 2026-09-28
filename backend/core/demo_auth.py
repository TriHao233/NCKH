import base64
import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Any

from core.config import resolve_path, settings

DEMO_TOKEN_PREFIX = "demo"


def _urlsafe_b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _urlsafe_b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode((value + "=" * (-len(value) % 4)).encode("ascii"))


def _credentials_path() -> Path:
    path = Path(settings.firebase_credentials_path).expanduser()
    return path if path.is_absolute() else resolve_path(path)


def _demo_secret() -> bytes:
    if settings.demo_session_secret:
        return settings.demo_session_secret.encode("utf-8")
    try:
        credential = json.loads(_credentials_path().read_text(encoding="utf-8"))
        private_key = credential.get("private_key")
        if private_key:
            return private_key.encode("utf-8")
    except Exception:
        pass
    return f"{settings.app_name}:{settings.firebase_credentials_path}".encode("utf-8")


def _sign(payload_segment: str) -> str:
    digest = hmac.new(_demo_secret(), payload_segment.encode("ascii"), hashlib.sha256).digest()
    return _urlsafe_b64encode(digest)


def create_demo_session_token(user: dict[str, Any]) -> str:
    now = int(time.time())
    ttl_seconds = max(1, settings.demo_session_ttl_hours) * 3600
    payload = {
        "typ": DEMO_TOKEN_PREFIX,
        "uid": user["firebase_uid"],
        "email": user.get("email", ""),
        "name": user.get("display_name", ""),
        "role": user.get("role", ""),
        "iat": now,
        "exp": now + ttl_seconds,
    }
    payload_segment = _urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    return f"{DEMO_TOKEN_PREFIX}.{payload_segment}.{_sign(payload_segment)}"


def is_demo_session_token(token: str) -> bool:
    return token.startswith(f"{DEMO_TOKEN_PREFIX}.")


def verify_demo_session_token(token: str) -> dict[str, Any]:
    if not settings.demo_mode:
        raise ValueError("Demo login is disabled")
    try:
        prefix, payload_segment, signature = token.split(".", 2)
    except ValueError as exc:
        raise ValueError("Malformed demo token") from exc
    if prefix != DEMO_TOKEN_PREFIX:
        raise ValueError("Invalid demo token prefix")
    expected_signature = _sign(payload_segment)
    if not hmac.compare_digest(signature, expected_signature):
        raise ValueError("Invalid demo token signature")

    payload = json.loads(_urlsafe_b64decode(payload_segment))
    if int(payload.get("exp") or 0) < int(time.time()):
        raise ValueError("Demo token expired")
    if payload.get("typ") != DEMO_TOKEN_PREFIX or not payload.get("uid"):
        raise ValueError("Invalid demo token payload")
    return {
        "uid": payload["uid"],
        "email": payload.get("email", ""),
        "name": payload.get("name", ""),
        "demo": True,
    }
