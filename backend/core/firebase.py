import logging
import json
from pathlib import Path

import firebase_admin
from firebase_admin import credentials

from core.config import resolve_path, settings

logger = logging.getLogger(__name__)


def init_firebase() -> None:
    """Initialize the Firebase identity adapter exactly once."""
    if firebase_admin._apps:
        return
    credentials_path = Path(settings.firebase_credentials_path).expanduser()
    if not credentials_path.is_absolute():
        credentials_path = resolve_path(credentials_path)
    service_account = json.loads(credentials_path.read_text(encoding="utf-8"))
    credential_project_id = service_account.get("project_id")
    if credential_project_id != settings.firebase_project_id:
        raise RuntimeError(
            "Firebase service account project mismatch: "
            f"expected {settings.firebase_project_id}, got {credential_project_id or 'unknown'}"
        )
    credential = credentials.Certificate(str(credentials_path))
    firebase_admin.initialize_app(credential, {"projectId": settings.firebase_project_id})
    logger.info("Firebase Admin initialized for project %s", settings.firebase_project_id)
