import logging
from contextlib import contextmanager
from threading import Lock
from typing import Iterator

import certifi
from pymongo import MongoClient
from pymongo.client_session import ClientSession
from pymongo.database import Database

from core.config import settings

logger = logging.getLogger(__name__)

_mongo_client: MongoClient | None = None
_client_lock = Lock()


def get_mongo_client() -> MongoClient:
    """Return the single Mongo client configured from backend/.env."""
    global _mongo_client
    if _mongo_client is not None:
        return _mongo_client

    with _client_lock:
        if _mongo_client is None:
            options = {
                "serverSelectionTimeoutMS": settings.mongo_connect_timeout_ms,
                "tz_aware": True,
            }
            if settings.mongo_uri.startswith("mongodb+srv://") or "tls=true" in settings.mongo_uri.lower():
                options["tlsCAFile"] = certifi.where()
            _mongo_client = MongoClient(settings.mongo_uri, **options)
    return _mongo_client


def get_database() -> Database:
    return get_mongo_client()[settings.db_name]


# Compatibility aliases for existing OCR/RAG modules. V2 intentionally uses one
# database so cross-domain references can be validated consistently.
def get_auth_db() -> Database:
    return get_database()


def get_rag_db() -> Database:
    return get_database()


def ping_database() -> None:
    get_mongo_client().admin.command("ping")


@contextmanager
def mongo_transaction() -> Iterator[ClientSession]:
    """Run an atomic write unit. MongoDB must be configured as a replica set."""
    with get_mongo_client().start_session() as session:
        with session.start_transaction():
            yield session


def close_database() -> None:
    global _mongo_client
    with _client_lock:
        if _mongo_client is not None:
            _mongo_client.close()
            _mongo_client = None
