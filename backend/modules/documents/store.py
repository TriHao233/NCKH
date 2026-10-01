"""Select the document aggregate source for API, OCR and RAG code paths."""

from core.config import settings
from core.database import get_database
from modules.documents.postgres_repository import PostgresDocumentRepository
from modules.documents.repository import MongoDocumentRepository


def get_document_repository(database=None):
    if settings.document_store == "postgres":
        return PostgresDocumentRepository()
    if settings.document_store == "mongo":
        return MongoDocumentRepository(database if database is not None else get_database())
    raise ValueError("DOCUMENT_STORE must be mongo or postgres")
