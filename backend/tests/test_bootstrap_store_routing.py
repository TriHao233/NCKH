from types import SimpleNamespace

from core import bootstrap
from core.config import settings


def test_bootstrap_does_not_create_document_or_ai_collections_in_postgres_mode(monkeypatch):
    monkeypatch.setattr(settings, "document_store", "postgres")
    monkeypatch.setattr(settings, "ai_config_store", "postgres")
    monkeypatch.setattr(settings, "moodle_target_store", "postgres")
    monkeypatch.setattr(settings, "user_store", "postgres")
    monkeypatch.setattr(settings, "catalog_store", "postgres")
    monkeypatch.setattr(settings, "dictionary_store", "postgres")
    monkeypatch.setattr(settings, "notification_store", "postgres")
    monkeypatch.setattr(settings, "audit_store", "postgres")
    monkeypatch.setattr(settings, "auth_db_name", "test_auth")
    monkeypatch.setattr(settings, "rag_db_name", "test_rag")
    rag_db = SimpleNamespace(schema_meta=SimpleNamespace(update_one=lambda *_args, **_kwargs: None))
    monkeypatch.setattr(bootstrap, "get_auth_db",
                        lambda: (_ for _ in ()).throw(AssertionError("Auth Mongo used")))
    monkeypatch.setattr(bootstrap, "get_rag_db", lambda: rag_db)
    collections = []
    monkeypatch.setattr(bootstrap, "_ensure_collections",
                        lambda _database, names: collections.extend(names))
    monkeypatch.setattr(bootstrap, "_ensure_indexes", lambda: None)
    monkeypatch.setattr(bootstrap, "_seed_reference_data", lambda: None)

    bootstrap.bootstrap_database()

    assert "chunk_sets" in collections
    assert "document_chunks" in collections
    assert not {"documents", "document_jobs", "document_pages",
                "ai_models", "prompt_templates", "evaluation_policies",
                "moodle_targets", "users", "subjects", "keywords",
                "notifications", "audit_logs", "User"} & set(collections)


def test_ai_postgres_mode_does_not_seed_mongo_reference_data(monkeypatch):
    monkeypatch.setattr(settings, "ai_config_store", "postgres")
    monkeypatch.setattr(settings, "moodle_target_store", "postgres")
    monkeypatch.setattr(bootstrap, "get_rag_db", lambda: SimpleNamespace())
    bootstrap._seed_reference_data()


def test_bootstrap_skips_postgres_owned_collection_indexes(monkeypatch):
    for name in ("user_store", "catalog_store", "document_store", "audit_store",
                 "notification_store", "moodle_target_store", "llm_slot_store"):
        monkeypatch.setattr(settings, name, "postgres")
    blocked = {"users", "subjects", "documents", "document_jobs", "document_pages",
               "audit_logs", "notifications", "moodle_targets", "llm_slots"}

    class Collection:
        def create_index(self, *_args, **_kwargs):
            return None

        def create_indexes(self, *_args, **_kwargs):
            return None

    class Database:
        def __getattr__(self, name):
            if name in blocked:
                raise AssertionError(f"Mongo index requested for {name}")
            return Collection()

    monkeypatch.setattr(bootstrap, "get_auth_db",
                        lambda: (_ for _ in ()).throw(AssertionError("Auth Mongo used")))
    monkeypatch.setattr(bootstrap, "get_rag_db", Database)
    bootstrap._ensure_indexes()
