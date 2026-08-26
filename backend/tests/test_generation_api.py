import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.dependencies import CurrentUser, require_teacher_or_admin
from modules.documents.service import get_document_service
from modules.generation.generate import router


def user(role: str = "Teacher") -> CurrentUser:
    oid = ObjectId()
    return CurrentUser(
        id=oid,
        firebase_uid=f"firebase-{oid}",
        email="teacher@example.com",
        role=role,
        is_active=True,
        permissions=(),
    )


class GenerationStatusApiTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.current_user = user()
        self.app.dependency_overrides[require_teacher_or_admin] = lambda: self.current_user
        self.app.dependency_overrides[get_document_service] = lambda: type(
            "DocumentServiceStub",
            (),
            {"can_use": staticmethod(lambda _document_id, _user: True)},
        )()
        self.client = TestClient(self.app)
        self.job_id = str(ObjectId())

    def tearDown(self):
        self.app.dependency_overrides.clear()

    @staticmethod
    def queued_job(job_id: str) -> dict:
        now = datetime.now(timezone.utc)
        return {
            "job_id": job_id,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
        }

    def test_teacher_status_lookup_is_scoped_to_owner(self):
        with patch("modules.generation.generate.get_generation_job") as lookup:
            lookup.return_value = self.queued_job(self.job_id)
            response = self.client.get(f"/api/v1/generate/status/{self.job_id}")

        self.assertEqual(response.status_code, 200)
        lookup.assert_called_once_with(self.job_id, requested_by_user_id=self.current_user.id)

    def test_other_teacher_receives_not_found(self):
        with patch("modules.generation.generate.get_generation_job", return_value=None) as lookup:
            response = self.client.get(f"/api/v1/generate/status/{self.job_id}")

        self.assertEqual(response.status_code, 404)
        lookup.assert_called_once_with(self.job_id, requested_by_user_id=self.current_user.id)

    def test_admin_can_inspect_any_generation_job(self):
        self.current_user = user("Admin")
        with patch("modules.generation.generate.get_generation_job") as lookup:
            lookup.return_value = self.queued_job(self.job_id)
            response = self.client.get(f"/api/v1/generate/status/{self.job_id}")

        self.assertEqual(response.status_code, 200)
        lookup.assert_called_once_with(self.job_id, requested_by_user_id=None)

    @staticmethod
    def generation_payload() -> dict:
        return {
            "document_id": str(ObjectId()),
            "bloom_level": "2_hieu",
            "question_type": "dung_sai",
            "num_questions": 1,
        }

    def test_enqueue_reuses_job_for_same_idempotency_key(self):
        existing = self.queued_job(self.job_id)
        with (
            patch("modules.generation.generate.get_generation_job_by_idempotency", return_value=existing),
            patch("modules.generation.generate.count_active_generation_jobs") as count_active,
            patch("modules.generation.generate.create_generation_job") as create_job,
        ):
            response = self.client.post(
                "/api/v1/generate/questions",
                json=self.generation_payload(),
                headers={"Idempotency-Key": "request-123"},
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["job_id"], self.job_id)
        count_active.assert_not_called()
        create_job.assert_not_called()

    def test_enqueue_rejects_user_over_active_job_quota(self):
        with (
            patch("modules.generation.generate.get_generation_job_by_idempotency", return_value=None),
            patch("modules.generation.generate.count_active_generation_jobs", return_value=10),
            patch("modules.generation.generate.create_generation_job") as create_job,
        ):
            response = self.client.post(
                "/api/v1/generate/questions",
                json=self.generation_payload(),
                headers={"Idempotency-Key": "request-over-quota"},
            )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["Retry-After"], "15")
        create_job.assert_not_called()


if __name__ == "__main__":
    unittest.main()
