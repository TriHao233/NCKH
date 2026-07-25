import inspect
import unittest

from bson import ObjectId
from pydantic import ValidationError

from core.bootstrap import VALIDATORS
from core.config import settings
from modules.documents.schemas import DocumentStatus
from modules.documents.service import DocumentService
from modules.generation.schemas import (
    BloomLevel,
    GeneratedQuestion,
    GenerationPlanSummary,
    QuestionGenerateRequest,
    QuestionType,
)
from modules.questions.schemas import QuestionCreateRequest, QuestionUpdateRequest
from modules.questions.service import QuestionService, stable_hash
from modules.questions.workflow_schemas import (
    AutoEvaluationRequest,
    MoodlePublicationRequest,
    ReviewOverride,
)
from modules.users.schemas import PublicRegisterRequest, RoleEnum


class SchemaV2Tests(unittest.TestCase):
    def test_only_admin_teacher_and_reviewer_roles_exist(self):
        self.assertEqual({role.value for role in RoleEnum}, {"Admin", "Teacher", "Reviewer"})

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

    def test_auto_evaluation_requires_expected_version(self):
        with self.assertRaises(ValidationError):
            AutoEvaluationRequest()

        payload = AutoEvaluationRequest(expected_version=1)
        self.assertEqual(payload.evaluator_model_code, "qwen")
        self.assertTrue(payload.fallback_to_heuristic)

    def test_moodle_publication_request_has_demo_defaults(self):
        payload = MoodlePublicationRequest(expected_version=1)
        self.assertEqual(payload.moodle_site_id, "demo-moodle")
        self.assertTrue(payload.mock)

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

    def test_generation_request_accepts_question_plan(self):
        req = QuestionGenerateRequest(
            document_id="507f1f77bcf86cd799439011",
            bloom_level=BloomLevel.HIEU,
            question_plan=[
                {"question_type": QuestionType.TRAC_NGHIEM, "bloom_level": BloomLevel.HIEU, "num_questions": 3},
                {"question_type": QuestionType.DUNG_SAI, "bloom_level": BloomLevel.PHAN_TICH, "num_questions": 2},
            ],
            instruction="Tập trung vào cây nhị phân tìm kiếm.",
        )

        self.assertEqual(sum(item.num_questions for item in req.effective_plan()), 5)
        self.assertEqual(req.effective_plan()[1].bloom_level, BloomLevel.PHAN_TICH)
        self.assertEqual(req.instruction, "Tập trung vào cây nhị phân tìm kiếm.")

    def test_generation_request_rejects_oversized_plan(self):
        with self.assertRaises(ValidationError):
            QuestionGenerateRequest(
                document_id="507f1f77bcf86cd799439011",
                bloom_level=BloomLevel.HIEU,
                question_plan=[
                    {"question_type": QuestionType.TRAC_NGHIEM, "num_questions": 10},
                    {"question_type": QuestionType.DUNG_SAI, "num_questions": 10},
                    {"question_type": QuestionType.DIEN_KHUYET, "num_questions": 1},
                ],
            )

    def test_generated_question_can_return_persisted_metadata(self):
        question = GeneratedQuestion(
            question="Cấu trúc dữ liệu nào dùng nguyên tắc FIFO?",
            options={"A": "Stack", "B": "Queue", "C": "Tree", "D": "Graph"},
            correct_answer="B",
            explanation="Queue xử lý phần tử vào trước ra trước.",
            question_type="trac_nghiem",
            bloom_level="hieu",
            source_context="Queue là hàng đợi FIFO.",
            question_id="507f1f77bcf86cd799439011",
            question_code="Q-507F1F77BCF86CD799439011",
            current_version=1,
            current_version_id="507f1f77bcf86cd799439012",
        )

        self.assertEqual(question.question_id, "507f1f77bcf86cd799439011")
        self.assertEqual(question.current_version, 1)

    def test_generation_plan_summary_reports_shortfall(self):
        summary = GenerationPlanSummary(
            plan_index=2,
            question_type="trac_nghiem",
            bloom_level="phan_tich",
            requested_count=5,
            parsed_count=5,
            valid_count=4,
            duplicate_count=1,
            saved_count=3,
            skipped_count=2,
            warnings=["Bỏ 1 câu trùng nội dung.", "Lưu thiếu 2 câu so với yêu cầu."],
        )

        self.assertEqual(summary.plan_index, 2)
        self.assertEqual(summary.skipped_count, 2)
        self.assertIn("Lưu thiếu 2 câu so với yêu cầu.", summary.warnings)

    def test_key_validators_require_schema_version(self):
        for collection in ("users", "documents", "questions", "question_versions"):
            required = VALIDATORS[collection]["$jsonSchema"]["required"]
            self.assertIn("schema_version", required)

    def test_user_validator_accepts_reviewer_role(self):
        role_enum = set(VALIDATORS["users"]["$jsonSchema"]["properties"]["role"]["enum"])
        self.assertEqual(role_enum, {role.value for role in RoleEnum})

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
