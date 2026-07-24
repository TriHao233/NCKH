import inspect
import unittest

from bson import ObjectId
from pydantic import ValidationError

from core.bootstrap import VALIDATORS
from core.config import settings
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
        self.assertIn("references", inspect.signature(QuestionService).parameters)

    def test_auth_and_rag_databases_are_separate(self):
        self.assertEqual(settings.auth_db_name, "NCKH")
        self.assertEqual(settings.rag_db_name, "rag_database")
        self.assertNotEqual(settings.auth_db_name, settings.rag_db_name)

    def test_key_validators_require_schema_version(self):
        for collection in ("users", "documents", "questions", "question_versions"):
            required = VALIDATORS[collection]["$jsonSchema"]["required"]
            self.assertIn("schema_version", required)

    def test_auth_user_is_minimal_uid_and_token_link(self):
        schema = VALIDATORS["User"]["$jsonSchema"]
        self.assertEqual(set(schema["required"]), {"uid", "token"})
        self.assertEqual(set(schema["properties"]), {"_id", "uid", "token"})
        self.assertFalse(schema["additionalProperties"])

    def test_question_sources_cannot_mix_documents(self):
        first_document_id = ObjectId()
        second_document_id = ObjectId()
        chunks = {
            ObjectId(): {
                "_id": ObjectId(),
                "document_id": first_document_id,
                "chunk_set_id": ObjectId(),
                "content": "A",
                "content_hash": "a",
            },
            ObjectId(): {
                "_id": ObjectId(),
                "document_id": second_document_id,
                "chunk_set_id": ObjectId(),
                "content": "B",
                "content_hash": "b",
            },
        }

        class References:
            def find_chunk(self, chunk_id):
                return chunks.get(chunk_id)

            def find_document(self, _document_id):
                return None

            def find_subject(self, _subject_id):
                return None

        service = QuestionService(repository=None, references=References())
        with self.assertRaises(ValueError):
            service._sources([str(chunk_id) for chunk_id in chunks])


if __name__ == "__main__":
    unittest.main()
