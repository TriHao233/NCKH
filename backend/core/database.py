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
_transactions_supported: bool | None = None


def get_mongo_client() -> MongoClient:
    """Return the single Mongo client configured from backend/.env."""
    global _mongo_client
    if _mongo_client is not None:
        return _mongo_client

    with _client_lock:
        if _mongo_client is None:
            options = {
                "serverSelectionTimeoutMS": settings.mongo_connect_timeout_ms,
                "retryWrites": False,
                "tz_aware": True,
            }
            if settings.mongo_uri.startswith("mongodb+srv://") or "tls=true" in settings.mongo_uri.lower():
                options["tlsCAFile"] = certifi.where()
            _mongo_client = MongoClient(settings.mongo_uri, **options)
    return _mongo_client


def get_auth_db() -> Database:
    """Database for Firebase-linked application user profiles."""
    return get_mongo_client()[settings.auth_db_name]


def get_rag_db() -> Database:
    """Database for the V2 document, RAG, and question-bank schema."""
    return get_mongo_client()[settings.rag_db_name]


def get_database() -> Database:
    """Compatibility alias for existing OCR/RAG modules."""
    return get_rag_db()


def ping_database() -> None:
    get_mongo_client().admin.command("ping")


def supports_transactions() -> bool:
    """Return whether the connected MongoDB topology can run transactions."""
    global _transactions_supported
    if _transactions_supported is not None:
        return _transactions_supported

    try:
        hello = get_mongo_client().admin.command("hello")
    except Exception:
        _transactions_supported = False
        return _transactions_supported

    _transactions_supported = bool(
        hello.get("setName")
        or hello.get("msg") == "isdbgrid"
    )
    if not _transactions_supported:
        logger.info(
            "MongoDB transactions are disabled because the server is not a replica set or mongos."
        )
    return _transactions_supported


@contextmanager
def mongo_transaction() -> Iterator[ClientSession | None]:
    """Run an atomic write unit when MongoDB supports transactions.

    Local standalone MongoDB instances cannot start transactions. When the
    requirement is explicitly disabled for development, callers receive
    ``None`` and PyMongo executes writes without a session.
    """
    if not supports_transactions():
        if settings.require_mongo_transactions:
            raise RuntimeError(
                "MongoDB transactions are required, but the connected server is not "
                "a replica set or mongos. Configure MONGO_URI with replicaSet or set "
                "REQUIRE_MONGO_TRANSACTIONS=false only for local development."
            )
        yield None
        return

    with get_mongo_client().start_session() as session:
        with session.start_transaction():
            yield session


def close_database() -> None:
    global _mongo_client, _transactions_supported
    with _client_lock:
        if _mongo_client is not None:
            _mongo_client.close()
            _mongo_client = None
            _transactions_supported = None
