import inspect
import unittest
from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId
from pydantic import ValidationError

from core.bootstrap import VALIDATORS
from core.config import settings
from core.dependencies import CurrentUser
from modules.admin.jobs_service import (
    AdminJobService,
    _generation_status_filter,
    _parse_object_id,
    _uppercase_status_filter,
)
from modules.auth import login as auth_login
from modules.documents.schemas import DocumentStatus
from modules.documents.service import DocumentService
from modules.exams.service import ExamService, ExamVariantService
from modules.generation.schemas import (
    BloomLevel,
    GeneratedQuestion,
    GenerationPlanSummary,
    QuestionGenerateRequest,
    QuestionType,
)
from modules.generation.llm.deepseek import DeepseekProvider
from modules.generation.llm.factory import get_llm_service
from modules.generation.prompt_builder import PromptBuilder
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
from modules.users.schemas import (
    GenerationPresetPayload,
    PublicRegisterRequest,
    RoleEnum,
    UserAdminUpdateRequest,
)
from modules.users.service import UserService


def _current_user(role="Teacher", user_id=None):
    oid = user_id or ObjectId()
    return CurrentUser(
        id=oid,
        firebase_uid=f"firebase-{oid}",
        email=f"{role.lower()}@example.com",
        role=role,
        is_active=True,
    )


def _exam_doc(owner_id):
    now = datetime.now(timezone.utc)
    return {
        "_id": ObjectId(),
        "name": "Midterm",
        "exam_title": "Data Structures Midterm",
        "subject_id": ObjectId(),
        "question_count": 1,
        "header": {"school": "CTU"},
        "matrix": [],
        "questions": [],
        "status": "draft",
        "created_by_user_id": owner_id,
        "created_at": now,
        "updated_at": now,
    }


class FakeExamRepository:
    def __init__(self, exams=None, variants=None):
        self.exams = {str(exam["_id"]): exam for exam in (exams or [])}
        self.variants = variants or []

    def create(self, exam):
        self.exams[str(exam["_id"])] = exam
        return exam

    def find(self, exam_id):
        return self.exams.get(str(exam_id))

    def list(self, page, page_size, created_by_user_id):
        items = list(self.exams.values())
        if created_by_user_id is not None:
            items = [
                exam for exam in items
                if str(exam.get("created_by_user_id")) == str(created_by_user_id)
            ]
        return items, len(items)

    def update(self, exam_id, updates):
        exam = self.find(exam_id)
        if not exam:
            return None
        exam.update(updates)
        exam["updated_at"] = datetime.now(timezone.utc)
        return exam

    def delete(self, exam_id):
        return self.exams.pop(str(exam_id), None) is not None

    def count_variants(self, exam_id):
        return len([v for v in self.variants if str(v["exam_id"]) == str(exam_id)])


class FakeExamVariantRepository:
    def __init__(self, variants=None):
        self.variants = {str(variant["_id"]): variant for variant in (variants or [])}

    def create(self, variant):
        self.variants[str(variant["_id"])] = variant
        return variant

    def find(self, variant_id):
        return self.variants.get(str(variant_id))

    def list_by_exam(self, exam_id):
        return [
            variant for variant in self.variants.values()
            if str(variant["exam_id"]) == str(exam_id)
        ]

    def delete(self, variant_id):
        return self.variants.pop(str(variant_id), None) is not None


def _user_doc(role="Admin", is_active=True):
    now = datetime.now(timezone.utc)
    oid = ObjectId()
    return {
        "_id": oid,
        "firebase_uid": f"firebase-{oid}",
        "email": f"{role.lower()}-{oid}@example.com",
        "display_name": f"{role} User",
        "role": role,
        "profile": {"school": "", "address": "", "avatar": ""},
        "is_active": is_active,
        "created_at": now,
        "updated_at": now,
    }


class FakeUserRepository:
    def __init__(self, users):
        self.users = {str(user["_id"]): dict(user) for user in users}

    def find_by_id(self, user_id):
        return self.users.get(str(user_id))

    def update(self, user_id, fields):
        user = self.find_by_id(user_id)
        if not user:
            return None
        user.update(fields)
        user["updated_at"] = datetime.now(timezone.utc)
        return user

    def count_active_admins(self):
        return len([
            user for user in self.users.values()
            if user.get("role") == "Admin" and user.get("is_active", True)
        ])


class FakeIdentityGateway:
    def __init__(self):
        self.disabled_calls = []
        self.update_calls = []

    def create_user(self, *, email, password, display_name):
        raise NotImplementedError

    def update_user(self, firebase_uid, **fields):
        self.update_calls.append((firebase_uid, fields))

    def set_user_disabled(self, firebase_uid, disabled):
        self.disabled_calls.append((firebase_uid, disabled))

    def delete_user(self, firebase_uid):
        raise NotImplementedError


class FakeSessions:
    def __init__(self):
        self.upserts = []

    def upsert(self, firebase_uid, id_token):
        self.upserts.append((firebase_uid, id_token))


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

    def test_demo_login_route_registration_follows_demo_mode(self):
        route_paths = {route.path for route in auth_login.router.routes}
        self.assertEqual("/demo-login" in route_paths, settings.demo_mode)

    def test_teacher_cannot_access_another_teachers_exam(self):
        owner = _current_user("Teacher")
        other_teacher = _current_user("Teacher")
        exam = _exam_doc(owner.id)
        service = ExamService(FakeExamRepository([exam]), question_repository=None)

        with self.assertRaises(PermissionError):
            service.get_exam(str(exam["_id"]), other_teacher)

        result = service.get_exam(str(exam["_id"]), owner)
        self.assertEqual(result["id"], str(exam["_id"]))

    def test_admin_can_access_any_teacher_exam(self):
        owner = _current_user("Teacher")
        admin = _current_user("Admin")
        exam = _exam_doc(owner.id)
        service = ExamService(FakeExamRepository([exam]), question_repository=None)

        result = service.get_exam(str(exam["_id"]), admin)
        self.assertEqual(result["created_by_user_id"], str(owner.id))

    def test_variant_preview_enforces_exam_ownership(self):
        owner = _current_user("Teacher")
        other_teacher = _current_user("Teacher")
        exam = _exam_doc(owner.id)
        variant = {
            "_id": ObjectId(),
            "exam_id": exam["_id"],
            "exam_code": "A01",
            "questions": [],
            "answer_key": {},
            "created_at": datetime.now(timezone.utc),
        }
        service = ExamVariantService(
            FakeExamRepository([exam]),
            FakeExamVariantRepository([variant]),
        )

        with self.assertRaises(PermissionError):
            service.build_preview(str(exam["_id"]), str(variant["_id"]), other_teacher)

    def test_cannot_deactivate_last_active_admin(self):
        admin_doc = _user_doc("Admin", True)
        service = UserService(FakeUserRepository([admin_doc]), FakeIdentityGateway(), FakeSessions())
        actor = _current_user("Admin", admin_doc["_id"])

        with self.assertRaises(ValueError):
            service.deactivate(str(admin_doc["_id"]), actor)

    def test_cannot_downgrade_last_active_admin(self):
        admin_doc = _user_doc("Admin", True)
        identity = FakeIdentityGateway()
        service = UserService(FakeUserRepository([admin_doc]), identity, FakeSessions())
        actor = _current_user("Admin", admin_doc["_id"])

        with self.assertRaises(ValueError):
            service.update_admin(
                str(admin_doc["_id"]),
                UserAdminUpdateRequest(role="Teacher"),
                actor,
            )
        self.assertEqual(identity.disabled_calls, [])

    def test_admin_job_summary_tracks_operational_states(self):
        jobs = [
            {"status": "queued", "is_long_running": False},
            {"status": "PROCESSING", "is_long_running": True},
            {"status": "ERROR", "is_long_running": False},
            {"status": "STALE", "is_long_running": False},
            {"status": "COMPLETED", "is_long_running": False},
        ]

        summary = AdminJobService._summary(jobs)

        self.assertEqual(summary["total"], 5)
        self.assertEqual(summary["active"], 2)
        self.assertEqual(summary["failed"], 2)
        self.assertEqual(summary["long_running"], 1)

    def test_admin_job_search_matches_entity_and_error(self):
        job = {
            "id": "job-1",
            "kind": "evaluation",
            "type": "Evaluation",
            "status": "ERROR",
            "entity": {"id": "question-1", "label": "Binary tree"},
            "error_message": "Model timeout",
        }

        self.assertTrue(AdminJobService._matches_search(job, "binary"))
        self.assertTrue(AdminJobService._matches_search(job, "timeout"))
        self.assertFalse(AdminJobService._matches_search(job, "moodle"))

    def test_admin_job_rejects_invalid_object_id(self):
        with self.assertRaises(ValueError):
            _parse_object_id("not-an-object-id", "job_id")

    def test_admin_job_status_filters_support_rollups(self):
        self.assertEqual(_generation_status_filter("active"), {"$in": ["queued", "processing"]})
        self.assertEqual(_generation_status_filter("retryable"), {"$in": ["failed"]})
        self.assertEqual(_uppercase_status_filter("active"), {"$in": ["QUEUED", "PROCESSING"]})
        self.assertEqual(_uppercase_status_filter("retryable"), {"$in": ["FAILED", "ERROR", "STALE"]})

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

    def test_question_rule_is_loaded_into_generation_prompt(self):
        prompt = PromptBuilder().build(
            context="Stack hoạt động theo nguyên tắc LIFO.",
            bloom_level="hieu",
            question_type="trac_nghiem",
            num_questions=1,
        )

        self.assertIn("FORBIDDEN QUESTION RULES", prompt)
        self.assertIn("Do not create source-referencing questions", prompt)
        self.assertIn("If any rule is violated, reject the item and generate a replacement", prompt)

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

    def test_multi_answer_validation_allows_five_options(self):
        self.assertIsNone(
            _check_type_format(
                {
                    "question": "Câu hỏi mẫu?",
                    "options": {
                        "A": "Một",
                        "B": "Hai",
                        "C": "Ba",
                        "D": "Bốn",
                        "E": "Năm",
                    },
                    "correct_answer": "A, C, E",
                },
                "nhieu_lua_chon",
            )
        )

    def test_multi_answer_validation_rejects_all_options_correct(self):
        error = _check_type_format(
            {
                "question": "Câu hỏi mẫu?",
                "options": {"A": "Một", "B": "Hai", "C": "Ba", "D": "Bốn", "E": "Năm"},
                "correct_answer": "A, B, C, D, E",
            },
            "nhieu_lua_chon",
        )
        self.assertIn("không được chọn tất cả", error)

    def test_retry_prompt_allows_five_option_multi_answer_shape(self):
        prompt = _build_retry_prompt(
            original_prompt="ORIGINAL",
            question_type="nhieu_lua_chon",
            bloom_level="phan_tich",
            missing_count=3,
            validation_errors=["nhieu_lua_chon phải có 4 hoặc 5 lựa chọn"],
            avoid_questions=[],
        )
        self.assertIn('"A", "B", "C", "D", "E"', prompt)
        self.assertIn("Generate exactly 3 additional questions", prompt)

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
