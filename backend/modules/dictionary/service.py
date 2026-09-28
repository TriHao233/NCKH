"""Select one keyword store for chunking and AI keyword learning."""

from core.config import settings
from modules.dictionary import mongodb
from modules.dictionary.postgres_repository import PostgresDictionaryRepository


def _store():
    if settings.dictionary_store == "postgres":
        return PostgresDictionaryRepository()
    if settings.dictionary_store == "mongo":
        return mongodb
    raise ValueError("DICTIONARY_STORE must be mongo or postgres")


def init_default_dictionary(course_id: str = "it_fundamentals") -> None:
    _store().init_default_dictionary(course_id)


def get_active_keywords(course_id: str = "it_fundamentals") -> list[str]:
    return _store().get_active_keywords(course_id)


def add_pending_keywords(course_id: str, keywords: list[str]) -> None:
    _store().add_pending_keywords(course_id, keywords)
