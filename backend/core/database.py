import logging

import firebase_admin
from firebase_admin import credentials
from pymongo import MongoClient
from pymongo.database import Database

from core.config import settings

logger = logging.getLogger(__name__)

_mongo_client: MongoClient | None = None


def get_mongo_client() -> MongoClient:
    """Mongo client dùng chung cho toàn bộ backend (singleton)."""
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(settings.mongo_uri)
    return _mongo_client


def get_auth_db() -> Database:
    """Database chứa dữ liệu người dùng (module auth)."""
    return get_mongo_client()[settings.auth_db_name]


def get_rag_db() -> Database:
    """Database chứa tài liệu/chunk/câu hỏi (module ocr, rag, generation, dictionary)."""
    return get_mongo_client()[settings.rag_db_name]


def init_firebase() -> None:
    """Khởi tạo Firebase Admin đúng 1 lần khi app start."""
    if firebase_admin._apps:
        return
    try:
        cred = credentials.Certificate(settings.firebase_credentials_path)
        firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin initialized")
    except FileNotFoundError:
        logger.warning(
            "Không tìm thấy firebase-service-account.json tại %s — bỏ qua Firebase. "
            "Các API auth dùng Firebase sẽ không hoạt động cho tới khi bổ sung file này.",
            settings.firebase_credentials_path,
        )
