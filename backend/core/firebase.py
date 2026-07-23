import logging

import firebase_admin
from firebase_admin import credentials

from core.config import settings

logger = logging.getLogger(__name__)


def init_firebase() -> None:
    """Initialize the Firebase identity adapter exactly once."""
    if firebase_admin._apps:
        return
    credential = credentials.Certificate(settings.firebase_credentials_path)
    firebase_admin.initialize_app(credential)
    logger.info("Firebase Admin initialized")
