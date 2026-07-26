import inspect
import unittest
from pathlib import Path

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
from modules.generation.llm.deepseek import DeepseekProvider
from modules.generation.llm.factory import get_llm_service
from modules.generation.question import _build_retry_prompt, _check_type_format
from modules.questions.schemas import QuestionCreateRequest, QuestionUpdateRequest
from modules.questions.repository import MongoQuestionRepository
from modules.questions.service import QuestionService, stable_hash
from modules.questions.workflow_schemas import (
    AutoEvaluationRequest,
    MoodlePublicationRequest,
    ReviewOverride,
)
from modules.rag.search import _heading_matches_target, _normalize_heading_text
from modules.users.schemas import GenerationPresetPayload, PublicRegisterRequest, RoleEnum
from modules.users.service import UserService


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
        self.assertEqual(payload.evaluator_model_code, settings.evaluation_model_provider)
        self.assertFalse(payload.fallback_to_heuristic)

    def test_llm_factory_accepts_ollama_model_alias(self):
        provider = get_llm_service("ollama:qwen2.5:7b")
        self.assertIsInstance(provider, DeepseekProvider)
        self.assertEqual(provider.model_name, "qwen2.5:7b")

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
        for collection in ("users", "documents", "questions", "question_versions", "evaluation_jobs"):
            required = VALIDATORS[collection]["$jsonSchema"]["required"]
            self.assertIn("schema_version", required)

    def test_user_validator_accepts_reviewer_role(self):
        role_enum = set(VALIDATORS["users"]["$jsonSchema"]["properties"]["role"]["enum"])
        self.assertEqual(role_enum, {role.value for role in RoleEnum})

    def test_question_validator_accepts_ai_draft_status(self):
        review_status_enum = set(
            VALIDATORS["questions"]["$jsonSchema"]["properties"]["review_status"]["enum"]
        )
        self.assertIn("DRAFT", review_status_enum)

    def test_question_validator_accepts_evaluation_queue_statuses(self):
        evaluation_status_enum = set(
            VALIDATORS["questions"]["$jsonSchema"]["properties"]["evaluation_status"]["enum"]
        )
        self.assertIn("QUEUED", evaluation_status_enum)
        self.assertIn("ERROR", evaluation_status_enum)
        self.assertIn("STALE", evaluation_status_enum)

    def test_evaluation_job_validator_tracks_worker_statuses(self):
        status_enum = set(VALIDATORS["evaluation_jobs"]["$jsonSchema"]["properties"]["status"]["enum"])
        self.assertTrue({"QUEUED", "PROCESSING", "COMPLETED", "ERROR", "STALE"}.issubset(status_enum))

    def test_question_validator_allows_aggregate_owner(self):
        question_properties = VALIDATORS["questions"]["$jsonSchema"]["properties"]
        self.assertEqual(question_properties["created_by_user_id"]["bsonType"], ["objectId", "null"])

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

    def test_rag_heading_match_normalizes_vietnamese_text(self):
        normalized_target = _normalize_heading_text("do thi")
        self.assertTrue(
            _heading_matches_target({"heading": "Đồ thị"}, normalized_target)
        )

        normalized_target = _normalize_heading_text("cay nhi phan")
        self.assertTrue(
            _heading_matches_target(
                {"heading_path_text": "Cấu trúc dữ liệu > Cây nhị phân tìm kiếm"},
                normalized_target,
            )
        )
        self.assertFalse(
            _heading_matches_target({"heading": "Hàng đợi"}, normalized_target)
        )

    def test_output_format_keeps_question_type_option_shapes(self):
        prompt_path = Path(__file__).resolve().parents[1] / "prompts" / "output_format.txt"
        output_format = prompt_path.read_text(encoding="utf-8")

        self.assertIn("trac_nghiem", output_format)
        self.assertIn('"A", "B", "C", "D"', output_format)
        self.assertIn("dung_sai", output_format)
        self.assertIn('"A": "Đúng", "B": "Sai"', output_format)

    def test_mcq_validation_rejects_two_option_shape(self):
        error = _check_type_format(
            {
                "question": "Câu hỏi mẫu?",
                "options": {"A": "Một", "B": "Hai"},
                "correct_answer": "A",
            },
            "trac_nghiem",
        )
        self.assertIn("4 lựa chọn", error)

        self.assertIsNone(
            _check_type_format(
                {
                    "question": "Câu hỏi mẫu?",
                    "options": {"A": "Một", "B": "Hai", "C": "Ba", "D": "Bốn"},
                    "correct_answer": "A",
                },
                "trac_nghiem",
            )
        )

    def test_retry_prompt_reinforces_mcq_option_shape(self):
        prompt = _build_retry_prompt(
            original_prompt="ORIGINAL",
            question_type="trac_nghiem",
            bloom_level="hieu",
            missing_count=2,
            validation_errors=["trac_nghiem phải có đúng 4 lựa chọn A/B/C/D"],
            avoid_questions=["Câu đã nhận"],
        )
        self.assertIn('exactly "A", "B", "C", "D"', prompt)
        self.assertIn("Generate exactly 2 additional questions", prompt)

    def test_generation_preset_payload_limits_plan_rows(self):
        payload = GenerationPresetPayload(
            name="Ôn tập demo",
            planItems=[
                {"questionTypeId": "mcq", "bloomId": "understand", "count": 2},
            ],
            instruction="Tập trung vào cây nhị phân.",
        )
        self.assertEqual(payload.planItems[0].count, 2)

        with self.assertRaises(ValidationError):
            GenerationPresetPayload(
                name="Sai số lượng",
                planItems=[
                    {"questionTypeId": "mcq", "bloomId": "understand", "count": 11},
                ],
            )

    def test_user_service_caps_generation_presets_per_user(self):
        class FakeUserRepository:
            def __init__(self):
                self.user = {
                    "_id": ObjectId(),
                    "generation_presets": [],
                }

            def find_by_id(self, _user_id):
                return self.user

            def update(self, _user_id, fields):
                self.user.update(fields)
                return self.user

        repository = FakeUserRepository()
        service = UserService(repository=repository, identity=None, sessions=None)
        user_id = str(repository.user["_id"])

        for index in range(13):
            service.save_generation_preset(
                user_id,
                GenerationPresetPayload(
                    name=f"Preset {index}",
                    planItems=[
                        {"questionTypeId": "mcq", "bloomId": "understand", "count": 1},
                    ],
                ),
            )

        presets = service.list_generation_presets(user_id)["items"]
        self.assertEqual(len(presets), 12)
        self.assertEqual(presets[0]["name"], "Preset 12")
        self.assertNotIn("Preset 0", {preset["name"] for preset in presets})

        self.assertTrue(service.delete_generation_preset(user_id, presets[0]["id"]))
        self.assertEqual(len(service.list_generation_presets(user_id)["items"]), 11)

    def test_question_repository_list_pushes_reviewer_filters_to_mongo(self):
        class FakeQuestionsCollection:
            def __init__(self):
                self.pipeline = None

            def aggregate(self, pipeline):
                self.pipeline = pipeline
                return [{"items": [], "count": [{"total": 0}]}]

        class FakeDatabase:
            def __init__(self):
                self.questions = FakeQuestionsCollection()

        fake_db = FakeDatabase()
        repo = MongoQuestionRepository(fake_db)
        document_id = ObjectId()

        pairs, total = repo.list(
            2,
            10,
            "PENDING",
            "queue",
            question_type="trac_nghiem",
            bloom_level=3,
            document_id=str(document_id),
            quality_color="green",
            min_score=0.8,
            publication_status="NOT_PUBLISHED",
            evaluation_status="PASSED",
        )

        self.assertEqual(pairs, [])
        self.assertEqual(total, 0)
        pipeline = fake_db.questions.pipeline
        self.assertIsNotNone(pipeline)
        question_match = pipeline[0]["$match"]
        self.assertEqual(question_match["review_status"], "PENDING")
        self.assertEqual(question_match["publication_status"], "NOT_PUBLISHED")
        self.assertEqual(question_match["evaluation_status"], "PASSED")
        self.assertEqual(question_match["quality_summary.color"], "GREEN")
        self.assertEqual(question_match["quality_summary.overall_score"], {"$gte": 0.8})

        version_match = pipeline[3]["$match"]
        self.assertEqual(version_match["version.classification.assessment_type"], "TRAC_NGHIEM")
        self.assertEqual(version_match["version.classification.bloom.level"], 3)
        self.assertEqual(version_match["version.document_id"], document_id)

        search_match = pipeline[4]["$match"]
        self.assertIn({"question_code": {"$regex": "queue", "$options": "i"}}, search_match["$or"])
        self.assertIn({"version.content": {"$regex": "queue", "$options": "i"}}, search_match["$or"])
        facet = pipeline[-1]["$facet"]
        self.assertEqual(facet["items"][0], {"$skip": 10})
        self.assertEqual(facet["items"][1], {"$limit": 10})


if __name__ == "__main__":
    unittest.main()
