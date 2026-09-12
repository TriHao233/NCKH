from pathlib import Path

import firebase_admin
from firebase_admin import auth

from core.config import resolve_path, settings


def _credentials_path() -> Path:
    path = Path(settings.firebase_credentials_path).expanduser()
    return path if path.is_absolute() else resolve_path(path)


def verify_firebase_id_token(id_token: str, *, clock_skew_seconds: int = 0) -> dict:
    """Verify Firebase ID tokens against the single configured Admin project."""
    claims = auth.verify_id_token(
        id_token,
        app=firebase_admin.get_app(),
        clock_skew_seconds=clock_skew_seconds,
    )
    project_id = settings.firebase_project_id
    if claims.get("aud") != project_id or claims.get("iss") != f"https://securetoken.google.com/{project_id}":
        raise ValueError("Firebase ID token belongs to a different project")
    return claims
