from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from bson import ObjectId
from fastapi.testclient import TestClient

from core.config import settings
from core.dependencies import get_current_user
from main import app
from modules.admin.overview_service import AdminOverviewService
from modules.admin.overview_router import get_admin_overview_service
from modules.documents.postgres_repository import PostgresDocumentRepository
from test_schema_v2 import InMemoryCollection, _current_user


def database():
    owner, subject, document_id = ObjectId(), ObjectId(), ObjectId()
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    row = {"_id": document_id, "schema_version": 2, "title": "Lecture", "original_filename": "lecture.pdf",
           "uploaded_by_user_id": owner, "subject_id": subject, "status": "FAILED", "archived_at": None,
           "page_count": 5, "current_version": 1, "created_at": now, "updated_at": now,
           "latest_error": {"message": "OCR failed", "traceback": "private"},
           "original_uri": "private/path", "artifacts": [{"uri": "private"}]}
    db = SimpleNamespace(documents=InMemoryCollection([row, {**row, "_id": ObjectId(), "archived_at": now}]),
        users=InMemoryCollection([{"_id": owner, "display_name": "Teacher", "email": "teacher@example.test"}]),
        subjects=InMemoryCollection([{"_id": subject, "subject_name": "Algorithms", "subject_code": "ALG"}]))
    return db, row


def test_document_monitor_filters_paginates_and_excludes_private_artifacts():
    db, row = database()
    service = AdminOverviewService(db)
    result = service.list_documents(1, 20, "FAILED", "lecture")
    assert result["total"] == 1
    item = result["items"][0]
    assert item["id"] == str(row["_id"])
    assert item["owner"]["display_name"] == "Teacher"
    assert item["subjects"][0]["name"] == "Algorithms"
    assert item["error_message"] == "OCR failed"
    assert "original_uri" not in item and "artifacts" not in item and "latest_error" not in item
    assert service.list_documents(2, 1, None, None)["items"] == []
    assert service.list_documents(1, 20, "READY", None)["total"] == 0
    owner_id, subject_id = str(row["uploaded_by_user_id"]), str(row["subject_id"])
    assert service.list_documents(1, 20, None, None, subject_id, owner_id)["total"] == 1
    assert service.list_documents(1, 20, None, None, None, str(ObjectId()))["total"] == 0
    assert service.list_documents(1, 20, None, None, str(ObjectId()), None)["total"] == 0


def test_document_monitor_uses_postgres_repository_without_mongo_reads(monkeypatch):
    for key in ("document_store", "user_store", "catalog_store"):
        monkeypatch.setattr(settings, key, "postgres")
    monkeypatch.setattr("modules.documents.postgres_repository.get_database", lambda: SimpleNamespace(documents=None))
    row = {"_id": ObjectId(), "title": "Postgres", "status": "READY"}
    listing = Mock(return_value=([row], 1))
    monkeypatch.setattr(PostgresDocumentRepository, "list", listing)
    result = AdminOverviewService(SimpleNamespace()).list_documents(2, 10, "READY", "Postgres")
    listing.assert_called_once_with(2, 10, "READY", "Postgres")
    assert result["items"][0]["title"] == "Postgres"


def test_document_monitor_route_is_admin_only_and_validates_filters():
    db, _ = database()
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_admin_overview_service] = lambda: AdminOverviewService(db)
    client = TestClient(app)
    try:
        app.dependency_overrides[get_current_user] = lambda: _current_user("Teacher")
        assert client.get(f"{settings.api_prefix}/admin/overview/documents").status_code == 403
        app.dependency_overrides[get_current_user] = lambda: _current_user("Admin")
        assert client.get(f"{settings.api_prefix}/admin/overview/documents").status_code == 200
        for params in ({"status": "ARCHIVED"}, {"page": 0}, {"page_size": 101}, {"search": "a" * 201}):
            assert client.get(f"{settings.api_prefix}/admin/overview/documents", params=params).status_code == 422
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
