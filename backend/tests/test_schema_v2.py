import inspect
import unittest

from pydantic import ValidationError

from modules.documents.schemas import DocumentStatus
from modules.documents.service import DocumentService
from modules.questions.schemas import QuestionCreateRequest, QuestionUpdateRequest
from modules.questions.service import QuestionService, stable_hash
from modules.questions.workflow_schemas import ReviewOverride
from modules.users.schemas import PublicRegisterRequest, RoleEnum


class SchemaV2Tests(unittest.TestCase):
    def test_only_admin_and_teacher_roles_exist(self):
        self.assertEqual({role.value for role in RoleEnum}, {"Admin", "Teacher"})

    def test_public_register_cannot_choose_role(self):
        with self.assertRaises(ValidationError):
            PublicRegisterRequest(
                email="teacher@example.com",
                password="secret1",
                full_name="Teacher",
                role="Admin",
            )

    def test_question_update_requires_optimistic_version(self):
        with self.assertRaises(ValidationError):
            QuestionUpdateRequest(content="Updated")

    def test_question_can_reference_multiple_chunks(self):
        payload = QuestionCreateRequest(
            content="Question",
            source_chunk_ids=["507f1f77bcf86cd799439011", "507f1f77bcf86cd799439012"],
        )
        self.assertEqual(len(payload.source_chunk_ids), 2)

    def test_review_override_requires_reason(self):
        with self.assertRaises(ValidationError):
            ReviewOverride(applied=True, score=0.9)

    def test_question_hash_is_order_independent(self):
        self.assertEqual(
            stable_hash({"content": "Q", "data": {"a": 1, "b": 2}}),
            stable_hash({"data": {"b": 2, "a": 1}, "content": "Q"}),
        )

    def test_document_has_archive_state(self):
        self.assertIn(DocumentStatus.ARCHIVED, set(DocumentStatus))

    def test_services_depend_on_abstractions_via_constructor(self):
        self.assertIn("repository", inspect.signature(DocumentService).parameters)
        self.assertIn("repository", inspect.signature(QuestionService).parameters)


if __name__ == "__main__":
    unittest.main()
