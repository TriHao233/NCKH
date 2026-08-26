import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.dependencies import CurrentUser, require_teacher_or_admin
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


if __name__ == "__main__":
    unittest.main()
