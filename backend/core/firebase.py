import logging
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
    credential = credentials.Certificate(str(credentials_path))
    firebase_admin.initialize_app(credential)
    logger.info("Firebase Admin initialized")
