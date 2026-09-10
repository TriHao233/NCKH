from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.dependencies import CurrentUser, get_current_user
from modules.catalog.router import router
from modules.catalog.service import CatalogConflictError, get_catalog_service


def current_user(role: str) -> CurrentUser:
    user_id = ObjectId()
    permissions = ("admin.catalog",) if role == "Admin" else ("catalog.subjects.manage_own",)
    return CurrentUser(
        id=user_id,
        firebase_uid=f"firebase-{user_id}",
        email=f"{role.lower()}@example.com",
        role=role,
        is_active=True,
        permissions=permissions,
        display_name=f"{role} User",
    )


class FakeCatalogService:
    def __init__(self):
        self.created = []
        self.error = None

    def create_subject(self, payload, user):
        if self.error:
            raise self.error
        self.created.append((payload, user))
        return {
            "id": str(ObjectId()),
            "subject_code": payload.subject_code,
            "subject_name": payload.subject_name,
            "description": payload.description,
            "chapters": [],
            "learning_outcomes": [],
            "is_active": payload.is_active,
            "usage_counts": {},
            "owner_id": str(user.id),
            "owner_email": user.email,
            "can_manage": True,
        }


def make_client(user: CurrentUser, service: FakeCatalogService) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_catalog_service] = lambda: service
    return TestClient(app, raise_server_exceptions=False)


def test_admin_creates_subject_and_payload_is_normalized():
    service = FakeCatalogService()
    client = make_client(current_user("Admin"), service)

    response = client.post(
        "/api/v1/catalog/subjects",
        json={
            "subject_code": "  CTDL  ",
            "subject_name": "  Cấu trúc dữ liệu  ",
            "description": "  Môn cơ sở  ",
        },
    )

    assert response.status_code == 201
    assert response.json()["subject_code"] == "CTDL"
    assert response.json()["subject_name"] == "Cấu trúc dữ liệu"
    assert len(service.created) == 1


def test_subject_name_is_required():
    service = FakeCatalogService()
    client = make_client(current_user("Admin"), service)

    response = client.post(
        "/api/v1/catalog/subjects",
        json={"subject_code": "CTDL", "subject_name": "   "},
    )

    assert response.status_code == 422
    assert service.created == []


def test_subject_code_is_required():
    service = FakeCatalogService()
    client = make_client(current_user("Admin"), service)

    response = client.post(
        "/api/v1/catalog/subjects",
        json={"subject_code": "   ", "subject_name": "Cấu trúc dữ liệu"},
    )

    assert response.status_code == 422
    assert service.created == []


def test_duplicate_subject_code_returns_conflict():
    service = FakeCatalogService()
    service.error = CatalogConflictError("Mã môn học đã tồn tại")
    client = make_client(current_user("Admin"), service)

    response = client.post(
        "/api/v1/catalog/subjects",
        json={"subject_code": "CTDL", "subject_name": "Cấu trúc dữ liệu"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Mã môn học đã tồn tại"}


def test_teacher_cannot_create_subject():
    service = FakeCatalogService()
    client = make_client(current_user("Teacher"), service)

    response = client.post(
        "/api/v1/catalog/subjects",
        json={"subject_code": "CTDL", "subject_name": "Cấu trúc dữ liệu"},
    )

    assert response.status_code == 403
    assert service.created == []


def test_database_error_returns_internal_server_error():
    service = FakeCatalogService()
    service.error = RuntimeError("database unavailable")
    client = make_client(current_user("Admin"), service)

    response = client.post(
        "/api/v1/catalog/subjects",
        json={"subject_code": "CTDL", "subject_name": "Cấu trúc dữ liệu"},
    )

    assert response.status_code == 500
