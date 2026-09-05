import unittest
from datetime import datetime, timezone

from bson import ObjectId
from core.access_policy import has_subject_access
from core.config import settings
from core.dependencies import CurrentUser
from modules.auth.session_repository import MongoFirebaseSessionRepository
from modules.generation.llm.model_registry import resolve_direct_model_snapshot
from modules.questions.workflow_schemas import MoodleExportItem, ReviewCreateRequest
from modules.questions.workflow_service import QuestionWorkflowService


def current_user(role="Reviewer", user_id=None, permissions=()):
    user_id = user_id or ObjectId()
    return CurrentUser(
        id=user_id,
        firebase_uid=f"firebase-{user_id}",
        email="user@example.edu",
        role=role,
        is_active=True,
        permissions=tuple(permissions),
    )


def matches(record, query):
    for key, expected in query.items():
        if key.startswith("$"):
            continue
        value = record
        for part in key.split("."):
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(part)
        if isinstance(expected, dict) and "$in" in expected:
            if value not in expected["$in"]:
                return False
        elif value != expected:
            return False
    return True


class Cursor(list):
    def sort(self, *_args, **_kwargs):
        return self


class Collection:
    def __init__(self, records=()):
        self.records = list(records)
        self.replacement = None

    def find_one(self, query, *_args, **_kwargs):
        return next((item for item in self.records if matches(item, query)), None)

    def find(self, query=None, *_args, **_kwargs):
        return Cursor(item for item in self.records if matches(item, query or {}))

    def find_one_and_replace(self, query, replacement, **_kwargs):
        self.replacement = replacement
        return replacement


class StageBContractTests(unittest.TestCase):
    def test_subject_scope_is_deny_by_default_and_allows_active_membership(self):
        user_id = ObjectId()
        subject_id = ObjectId()

        class Database:
            subjects = Collection([{"_id": subject_id, "is_active": True}])
            subject_memberships = Collection()

        database = Database()
        self.assertFalse(has_subject_access(database, user_id, subject_id))
        database.subject_memberships.records.append(
            {
                "user_id": user_id,
                "subject_id": subject_id,
                "status": "ACTIVE",
            }
        )
        self.assertTrue(has_subject_access(database, user_id, subject_id))

    def test_self_review_is_rejected_before_decision_is_written(self):
        reviewer = current_user()
        question_id = ObjectId()
        version_id = ObjectId()
        now = datetime.now(timezone.utc)

        class Database:
            questions = Collection(
                [
                    {
                        "_id": question_id,
                        "schema_version": 2,
                        "question_code": "Q-SELF",
                        "current_version": 1,
                        "current_version_id": version_id,
                        "lifecycle_status": "ACTIVE",
                        "review_status": "PENDING",
                        "evaluation_status": "PASSED",
                        "created_by_user_id": reviewer.id,
                        "review_assignment": {
                            "status": "IN_REVIEW",
                            "reviewer_user_id": reviewer.id,
                            "lock_expires_at": now,
                        },
                    }
                ]
            )
            question_versions = Collection(
                [
                    {
                        "_id": version_id,
                        "question_id": question_id,
                        "version": 1,
                        "created_by_user_id": reviewer.id,
                        "document_id": None,
                        "classification": {"subject": {"id": None}},
                    }
                ]
            )

        with self.assertRaises(PermissionError):
            QuestionWorkflowService(Database()).review(
                str(question_id),
                ReviewCreateRequest(expected_version=1, decision="APPROVED"),
                reviewer,
            )

    def test_bulk_export_is_atomic_when_one_version_is_not_eligible(self):
        reviewer = current_user(permissions=("questions.export_moodle",))
        approved_id, draft_id = ObjectId(), ObjectId()
        approved_version_id, draft_version_id = ObjectId(), ObjectId()

        def question(question_id, version_id, status):
            return {
                "_id": question_id,
                "schema_version": 2,
                "question_code": f"Q-{str(question_id)[-4:]}",
                "current_version": 1,
                "current_version_id": version_id,
                "approved_version_id": version_id if status == "APPROVED" else None,
                "lifecycle_status": "ACTIVE",
                "review_status": status,
                "created_by_user_id": ObjectId(),
            }

        def version(question_id, version_id):
            return {
                "_id": version_id,
                "question_id": question_id,
                "version": 1,
                "content": "Queue follows which rule?",
                "question_data": {"options": {"A": "FIFO", "B": "LIFO"}, "correct_answer": "A"},
                "classification": {"assessment_type": "TRAC_NGHIEM", "subject": {"id": None}},
            }

        class Database:
            questions = Collection(
                [question(approved_id, approved_version_id, "APPROVED"), question(draft_id, draft_version_id, "DRAFT")]
            )
            question_versions = Collection(
                [version(approved_id, approved_version_id), version(draft_id, draft_version_id)]
            )

        result = QuestionWorkflowService(Database()).export_moodle_bulk(
            [
                MoodleExportItem(question_id=str(approved_id), expected_version=1),
                MoodleExportItem(question_id=str(draft_id), expected_version=1),
            ],
            "gift",
            reviewer,
        )
        self.assertIsNone(result["content"])
        self.assertEqual(result["exported_count"], 0)
        self.assertEqual(result["errors"][0]["code"], "NOT_APPROVED")

    def test_local_only_rejects_cloud_and_remote_ollama_endpoint(self):
        old_policy = settings.inference_policy
        old_key = settings.gemini_api_key
        old_url = settings.ollama_generate_url
        try:
            settings.inference_policy = "LOCAL_ONLY"
            settings.gemini_api_key = "configured-for-test"
            with self.assertRaises(ValueError):
                resolve_direct_model_snapshot("gemini")
            settings.ollama_generate_url = "https://models.example.edu/api/generate"
            with self.assertRaises(ValueError):
                resolve_direct_model_snapshot("qwen")
        finally:
            settings.inference_policy = old_policy
            settings.gemini_api_key = old_key
            settings.ollama_generate_url = old_url

    def test_session_repository_discards_raw_bearer(self):
        database = {"User": Collection()}

        class Database(dict):
            pass

        repository = MongoFirebaseSessionRepository(Database(database))
        saved = repository.upsert("firebase-user", "raw-secret-token")
        self.assertIsNone(saved["token"])
        self.assertNotIn("raw-secret-token", repr(saved))


if __name__ == "__main__":
    unittest.main()
