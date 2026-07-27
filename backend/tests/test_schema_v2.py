import inspect
import re
import unittest
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bson import ObjectId
from pydantic import ValidationError

from core.bootstrap import SCHEMA_VERSION, VALIDATORS
from core.config import settings
from core.dependencies import CurrentUser
from core import job_recovery
from modules.admin.jobs_service import (
    AdminJobService,
    _generation_status_filter,
    _parse_object_id,
    _uppercase_status_filter,
)
from modules.admin.audit_service import AdminAuditService
from modules.admin.moodle_service import _safe_publication_item
from modules.admin.moodle_schemas import MoodleTargetPayload
from modules.admin.overview_service import AdminOverviewService
from modules.catalog.schemas import (
    AiModelActivationPayload,
    ChapterPayload,
    ChapterUpdatePayload,
    EvaluationPolicyActivationPayload,
    LearningOutcomePayload,
    LearningOutcomeUpdatePayload,
    PromptTemplateActivationPayload,
    SubjectUpdatePayload,
)
from modules.catalog.service import CatalogService
from modules.notifications.service import NotificationService
from modules.auth import login as auth_login
from modules.documents.schemas import DocumentStatus
from modules.documents.service import DocumentService
from modules.exams.service import ExamService, ExamVariantService
from modules.exams.schemas import ExamStatusUpdateRequest, ExamVariantCreateRequest
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
from modules.questions.schemas import (
    QuestionCreateRequest,
    QuestionResponse,
    QuestionSourceViewerResponse,
    QuestionUpdateRequest,
)
from modules.questions import repository as question_repository_module
from modules.questions.repository import MongoQuestionRepository
from modules.questions.service import QuestionService, stable_hash
from modules.questions.workflow_schemas import (
    AutoEvaluationRequest,
    MoodlePublicationRequest,
    ReviewAssignmentRequest,
    ReviewCreateRequest,
    ReviewOverride,
)
from modules.questions import workflow_service as question_workflow_module
from modules.questions.workflow_service import QuestionWorkflowService
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


class FakeExamQuestionRepository:
    def __init__(self, pairs=None):
        self.pairs = {str(question["_id"]): (question, version) for question, version in (pairs or [])}

    def find_pair(self, question_id):
        return self.pairs.get(str(question_id))

    def list(self, page, page_size, review_status, search, **filters):
        pairs = list(self.pairs.values())
        if review_status:
            pairs = [
                pair for pair in pairs
                if pair[0].get("review_status") == review_status
            ]
        subject_id = filters.get("subject_id")
        if subject_id:
            pairs = [
                pair for pair in pairs
                if str((pair[1].get("classification") or {}).get("subject", {}).get("id")) == str(subject_id)
            ]
        total = len(pairs)
        start = (page - 1) * page_size
        return pairs[start:start + page_size], total


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


def _path_values(record, path):
    parts = path.split(".")

    def walk(value, remaining):
        if not remaining:
            return [value]
        if isinstance(value, list):
            results = []
            for item in value:
                results.extend(walk(item, remaining))
            return results
        if not isinstance(value, dict):
            return []
        key = remaining[0]
        if key not in value:
            return []
        return walk(value[key], remaining[1:])

    return walk(record, parts)


def _matches_query(record, query):
    for key, expected in (query or {}).items():
        if key == "$or":
            if not any(_matches_query(record, item) for item in expected):
                return False
            continue
        if key == "$and":
            if not all(_matches_query(record, item) for item in expected):
                return False
            continue
        values = _path_values(record, key)
        if isinstance(expected, dict):
            for operator, operand in expected.items():
                if operator == "$in":
                    if not any(value in operand for value in values):
                        return False
                elif operator == "$lt":
                    if not any(value is not None and value < operand for value in values):
                        return False
                elif operator == "$lte":
                    if not any(value is not None and value <= operand for value in values):
                        return False
                elif operator == "$gt":
                    if not any(value is not None and value > operand for value in values):
                        return False
                elif operator == "$gte":
                    if not any(value is not None and value >= operand for value in values):
                        return False
                elif operator == "$exists":
                    if bool(values) is not bool(operand):
                        return False
                elif operator == "$regex":
                    flags = re.IGNORECASE if expected.get("$options") == "i" else 0
                    if not any(re.search(operand, str(value), flags) for value in values if value is not None):
                        return False
                elif operator == "$options":
                    continue
                else:
                    return False
        elif expected is None:
            if values and not any(value is None for value in values):
                return False
        elif not any(value == expected for value in values):
            return False
    return True


class InMemoryCursor(list):
    def sort(self, key_or_list, direction=1):
        if isinstance(key_or_list, list):
            sort_keys = key_or_list
        else:
            sort_keys = [(key_or_list, direction)]
        for key, sort_direction in reversed(sort_keys):
            self[:] = sorted(
                self,
                key=lambda item: (_path_values(item, key) or [None])[0],
                reverse=sort_direction == -1,
            )
        return self

    def skip(self, count):
        return InMemoryCursor(self[count:])

    def limit(self, count):
        return InMemoryCursor(self[:count])


class InMemoryCollection:
    def __init__(self, records=None):
        self.records = [dict(record) for record in (records or [])]

    def count_documents(self, query):
        return len([record for record in self.records if _matches_query(record, query)])

    def find(self, query=None, *_args, **_kwargs):
        return InMemoryCursor([record for record in self.records if _matches_query(record, query)])

    def find_one(self, query=None, *_args, **_kwargs):
        return next((record for record in self.records if _matches_query(record, query)), None)

    @staticmethod
    def _set_path(record, path, value, filter_query):
        if ".$." not in path:
            current = record
            parts = path.split(".")
            for part in parts[:-1]:
                current = current.setdefault(part, {})
            current[parts[-1]] = value
            return
        collection_key, field_key = path.split(".$.", 1)
        target_id = filter_query.get(f"{collection_key}._id")
        for item in record.get(collection_key, []):
            if item.get("_id") == target_id:
                item[field_key] = value
                return

    def insert_one(self, record, *_args, **_kwargs):
        item = dict(record)
        self.records.append(item)
        return type("Result", (), {"inserted_id": item.get("_id")})()

    def find_one_and_update(
        self,
        filter_query,
        update,
        *,
        upsert=False,
        return_document=None,
        **_kwargs,
    ):
        record = self.find_one(filter_query)
        if record is None and upsert:
            record = dict((update.get("$setOnInsert") or {}))
            record.update(update.get("$set") or {})
            self.records.append(record)
        if record is None:
            return None
        for path, value in (update.get("$set") or {}).items():
            self._set_path(record, path, value, filter_query)
        for path, value in (update.get("$push") or {}).items():
            record.setdefault(path, []).append(value)
        return record

    def update_one(self, filter_query, update, *, upsert=False, **_kwargs):
        matched = 0
        modified = 0
        record = self.find_one(filter_query)
        if record is None and upsert:
            record = dict(update.get("$setOnInsert") or {})
            self.records.append(record)
            matched = 1
            modified = 1
        elif record is not None:
            matched = 1

        if record is not None:
            changed = False
            for path, value in (update.get("$set") or {}).items():
                self._set_path(record, path, value, filter_query)
                changed = True
            for path, value in (update.get("$push") or {}).items():
                record.setdefault(path, []).append(value)
                changed = True
            if changed:
                modified = 1

        return type(
            "Result",
            (),
            {"matched_count": matched, "modified_count": modified},
        )()

    def update_many(self, filter_query, update, **_kwargs):
        matched = 0
        modified = 0
        for record in self.records:
            if not _matches_query(record, filter_query):
                continue
            matched += 1
            changed = False
            for path, value in (update.get("$set") or {}).items():
                self._set_path(record, path, value, filter_query)
                changed = True
            for path, value in (update.get("$push") or {}).items():
                record.setdefault(path, []).append(value)
                changed = True
            if changed:
                modified += 1

        return type(
            "Result",
            (),
            {"matched_count": matched, "modified_count": modified},
        )()


class FakeCatalogDatabase:
    def __init__(
        self,
        *,
        subjects=None,
        documents=None,
        question_versions=None,
        questions=None,
        exams=None,
        ai_models=None,
        prompt_templates=None,
        evaluation_policies=None,
    ):
        self.subjects = InMemoryCollection(subjects)
        self.documents = InMemoryCollection(documents)
        self.question_versions = InMemoryCollection(question_versions)
        self.questions = InMemoryCollection(questions)
        self.exams = InMemoryCollection(exams)
        self.ai_models = InMemoryCollection(ai_models)
        self.prompt_templates = InMemoryCollection(prompt_templates)
        self.evaluation_policies = InMemoryCollection(evaluation_policies)


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

    def test_question_restore_creates_new_version_and_resets_workflow(self):
        owner = _current_user("Teacher")
        question_id = ObjectId()
        version1_id = ObjectId()
        version2_id = ObjectId()
        review_id = ObjectId()
        reviewer_id = ObjectId()
        now = datetime.now(timezone.utc)
        classification = {
            "subject": {"id": None},
            "chapter": {"id": None},
            "assessment_type": "TRAC_NGHIEM",
            "bloom": {"level": 2, "code": "UNDERSTAND", "name": "Understand"},
            "difficulty": None,
        }
        version1_data = {
            "content": "Original stack question",
            "question_data": {
                "options": {"A": "LIFO", "B": "FIFO"},
                "correct_answer": "A",
                "explanation": "Stack pops the newest item first.",
            },
        }
        version2_data = {
            "content": "Edited queue question",
            "question_data": {
                "options": {"A": "LIFO", "B": "FIFO"},
                "correct_answer": "B",
                "explanation": "Queue removes the oldest item first.",
            },
        }
        versions = [
            {
                "_id": version1_id,
                "schema_version": SCHEMA_VERSION,
                "question_id": question_id,
                "version": 1,
                "origin": "MANUAL",
                "generation_run_id": None,
                "document_id": None,
                "created_by_user_id": owner.id,
                "generated_by_model_id": None,
                "classification": classification,
                "clos": [],
                "sources": [],
                "keywords": [],
                "content_hash": stable_hash(
                    {**version1_data, "classification": classification, "clos": [], "sources": []}
                ),
                "change_note": "Initial version",
                "created_at": now - timedelta(minutes=2),
                **version1_data,
            },
            {
                "_id": version2_id,
                "schema_version": SCHEMA_VERSION,
                "question_id": question_id,
                "version": 2,
                "origin": "MANUAL",
                "generation_run_id": None,
                "document_id": None,
                "created_by_user_id": owner.id,
                "generated_by_model_id": None,
                "classification": classification,
                "clos": [],
                "sources": [],
                "keywords": [],
                "content_hash": stable_hash(
                    {**version2_data, "classification": classification, "clos": [], "sources": []}
                ),
                "change_note": "Teacher edit",
                "created_at": now - timedelta(minutes=1),
                **version2_data,
            },
        ]
        question = {
            "_id": question_id,
            "schema_version": SCHEMA_VERSION,
            "question_code": "Q-RESTORE",
            "current_version": 2,
            "current_version_id": version2_id,
            "approved_version_id": version2_id,
            "lifecycle_status": "ACTIVE",
            "evaluation_status": "PASSED",
            "review_status": "APPROVED",
            "publication_status": "PUBLISHED",
            "quality_summary": {"overall_score": 0.92, "color": "GREEN"},
            "review_assignment": {
                "status": "CLAIMED",
                "reviewer_user_id": reviewer_id,
                "assigned_by_user_id": ObjectId(),
                "assigned_at": now - timedelta(minutes=5),
                "claimed_at": now - timedelta(minutes=4),
                "lock_expires_at": now + timedelta(minutes=30),
                "last_released_at": None,
                "release_reason": None,
            },
            "latest_review_id": review_id,
            "created_by_user_id": owner.id,
            "created_at": now - timedelta(minutes=3),
            "updated_at": now - timedelta(minutes=1),
            "archived_at": None,
        }
        db = FakeCatalogDatabase(questions=[question], question_versions=versions)
        original_transaction = question_repository_module.mongo_transaction
        try:
            question_repository_module.mongo_transaction = lambda: nullcontext(None)
            service = QuestionService(MongoQuestionRepository(db), references=None)

            history = service.versions(str(question_id), owner)
            restored = service.update(
                str(question_id),
                QuestionUpdateRequest(
                    expected_version=2,
                    content=version1_data["content"],
                    question_type=classification["assessment_type"],
                    bloom_level=classification["bloom"]["level"],
                    question_data=version1_data["question_data"],
                    source_chunk_ids=[],
                    clo_ids=[],
                    change_note="Restore from version 1",
                ),
                owner.id,
                actor_role=owner.role,
            )
            restored_history = service.versions(str(question_id), owner)
        finally:
            question_repository_module.mongo_transaction = original_transaction

        self.assertEqual([item["version"] for item in history], [2, 1])
        self.assertEqual(restored["current_version"], 3)
        self.assertEqual(restored["content"], version1_data["content"])
        self.assertEqual(restored["question_data"], version1_data["question_data"])
        self.assertEqual(restored["evaluation_status"], "NOT_STARTED")
        self.assertEqual(restored["review_status"], "PENDING")
        self.assertEqual(restored["publication_status"], "STALE")
        self.assertEqual(restored["quality_summary"], {})
        self.assertEqual(restored["review_assignment"]["status"], "UNASSIGNED")
        self.assertEqual([item["version"] for item in restored_history], [3, 2, 1])
        self.assertEqual(restored_history[0]["change_note"], "Restore from version 1")
        self.assertEqual(restored_history[0]["content"], version1_data["content"])

    def test_review_override_requires_reason(self):
        with self.assertRaises(ValidationError):
            ReviewOverride(applied=True, score=0.9)

    def test_structured_review_requires_reject_reason_and_revision_issue(self):
        with self.assertRaises(ValidationError):
            ReviewCreateRequest(expected_version=1, decision="REJECTED")

        with self.assertRaises(ValidationError):
            ReviewCreateRequest(
                expected_version=1,
                decision="NEEDS_REVISION",
                review_form={"overall_note": "Cần sửa đáp án."},
            )

        payload = ReviewCreateRequest(
            expected_version=1,
            decision="NEEDS_REVISION",
            review_form={
                "overall_note": "Cần sửa trước khi duyệt.",
                "revision_issues": [
                    {
                        "title": "Đáp án chưa khớp nguồn",
                        "severity": "HIGH",
                        "detail": "Nguồn nói FIFO nhưng đáp án chọn Stack.",
                        "page_number": 2,
                    }
                ],
            },
        )
        self.assertEqual(payload.review_form.revision_issues[0].severity, "HIGH")

    def test_review_assignment_request_allows_admin_unassign(self):
        payload = ReviewAssignmentRequest(reviewer_user_id=None, note="unassign")
        self.assertIsNone(payload.reviewer_user_id)
        self.assertEqual(payload.note, "unassign")

    def test_question_response_exposes_review_assignment(self):
        now = datetime.now(timezone.utc)
        response = QuestionResponse(
            id=str(ObjectId()),
            question_code="Q-1",
            current_version=1,
            current_version_id=str(ObjectId()),
            approved_version_id=None,
            document_id=None,
            lifecycle_status="ACTIVE",
            evaluation_status="PASSED",
            review_status="PENDING",
            publication_status="NOT_PUBLISHED",
            content="Question",
            question_data={},
            classification={},
            clos=[],
            sources=[],
            content_hash="hash",
            quality_summary={},
            review_assignment={
                "status": "IN_REVIEW",
                "reviewer_user_id": str(ObjectId()),
            },
            latest_review_id=None,
            created_at=now,
            updated_at=now,
        )
        self.assertEqual(response.review_assignment["status"], "IN_REVIEW")

    def test_question_source_viewer_schema_accepts_chunk_pages(self):
        response = QuestionSourceViewerResponse(
            question_id=str(ObjectId()),
            question_code="Q-1",
            version_id=str(ObjectId()),
            version=1,
            document={
                "id": str(ObjectId()),
                "title": "Document",
                "original_filename": "source.pdf",
                "page_count": 4,
                "current_ocr_job_id": str(ObjectId()),
                "current_chunk_set_id": str(ObjectId()),
                "pdf_available": True,
                "pdf_url": "/questions/q/source-pdf",
            },
            items=[
                {
                    "citation_order": 1,
                    "source_type": "CHUNK",
                    "is_primary": True,
                    "chunk_id": str(ObjectId()),
                    "page_range": {"start": 2, "end": 3, "pages": [2, 3]},
                    "context_excerpt": "Queue follows FIFO.",
                    "pages": [{"page_number": 2, "text": "Queue follows FIFO."}],
                }
            ],
        )
        self.assertEqual(response.items[0].pages[0].page_number, 2)

    def test_question_source_viewer_reports_stale_chunk_set_and_pages(self):
        question_id = ObjectId()
        version_id = ObjectId()
        document_id = ObjectId()
        old_chunk_set_id = ObjectId()
        current_chunk_set_id = ObjectId()
        ocr_job_id = ObjectId()
        chunk_id = ObjectId()
        now = datetime.now(timezone.utc)
        question = {
            "_id": question_id,
            "question_code": "Q-1",
            "current_version_id": version_id,
            "current_version": 1,
            "created_by_user_id": ObjectId(),
        }
        version = {
            "_id": version_id,
            "version": 1,
            "document_id": document_id,
            "created_by_user_id": question["created_by_user_id"],
            "sources": [
                {
                    "source_type": "CHUNK",
                    "chunk_id": chunk_id,
                    "chunk_set_id": old_chunk_set_id,
                    "chunk_content_hash": "hash-a",
                    "citation_order": 1,
                    "is_primary": True,
                    "context_excerpt": "Queue follows FIFO.",
                }
            ],
        }
        document = {
            "_id": document_id,
            "title": "Data Structures",
            "original_filename": "ctdl.pdf",
            "page_count": 5,
            "current_processing": {
                "ocr_job_id": ocr_job_id,
                "chunk_set_id": current_chunk_set_id,
            },
            "artifacts": [
                {
                    "type": "ORIGINAL_PDF",
                    "is_current": True,
                    "storage": {"provider": "LOCAL", "uri": "data/uploads/source.pdf"},
                    "mime_type": "application/pdf",
                }
            ],
        }
        chunk = {
            "_id": chunk_id,
            "document_id": document_id,
            "chunk_set_id": old_chunk_set_id,
            "chunk_no": 7,
            "content": "Queue follows FIFO.",
            "content_hash": "hash-a",
            "page_range": {"start": 2, "end": 3, "pages": [2, 3]},
            "heading": {"title": "Queue"},
        }

        class PairRepository:
            def find_pair(self, _question_id):
                return question, version

        class References:
            def find_chunk(self, requested_chunk_id):
                return chunk if requested_chunk_id == chunk_id else None

            def find_document(self, requested_document_id):
                return document if requested_document_id == document_id else None

            def find_pages(self, requested_document_id, requested_ocr_job_id, page_numbers):
                self.page_query = (requested_document_id, requested_ocr_job_id, page_numbers)
                return [
                    {
                        "page_number": 2,
                        "cleaned_text": "Page 2 Queue follows FIFO.",
                        "formula_blocks": [],
                    }
                ]

            def find_subject(self, _subject_id):
                return None

        references = References()
        service = QuestionService(repository=PairRepository(), references=references)
        result = service.source_viewer(str(question_id), _current_user("Reviewer"))

        self.assertEqual(result["document"]["title"], "Data Structures")
        self.assertTrue(result["document"]["pdf_available"])
        self.assertEqual(result["items"][0]["chunk_no"], 7)
        self.assertFalse(result["items"][0]["is_current_chunk_set"])
        self.assertIn("Nguồn không còn thuộc chunk set hiện hành", result["items"][0]["warnings"])
        self.assertEqual(result["items"][0]["pages"][0]["page_number"], 2)
        self.assertEqual(references.page_query, (document_id, ocr_job_id, [2, 3]))

    def test_reviewer_must_hold_active_review_lock(self):
        service = QuestionWorkflowService(database=None)
        reviewer_id = ObjectId()
        reviewer = _current_user("Reviewer", reviewer_id)
        now = datetime.now(timezone.utc)

        with self.assertRaises(PermissionError):
            service._ensure_review_lock(
                {"review_assignment": {"status": "ASSIGNED", "reviewer_user_id": reviewer_id}},
                reviewer,
                now,
            )

        service._ensure_review_lock(
            {
                "review_assignment": {
                    "status": "IN_REVIEW",
                    "reviewer_user_id": reviewer_id,
                    "lock_expires_at": (now + timedelta(minutes=1)).replace(tzinfo=None),
                }
            },
            reviewer,
            now,
        )

        with self.assertRaises(ValueError):
            service._ensure_review_lock(
                {
                    "review_assignment": {
                        "status": "IN_REVIEW",
                        "reviewer_user_id": reviewer_id,
                        "lock_expires_at": now - timedelta(minutes=1),
                    }
                },
                reviewer,
                now,
            )

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
        self.assertIsNone(payload.target_id)
        self.assertTrue(payload.mock)

    def test_moodle_publication_item_marks_mock_record(self):
        record = {
            "_id": ObjectId(),
            "question_id": ObjectId(),
            "question_version_id": ObjectId(),
            "question_version": 2,
            "publisher_user_id": ObjectId(),
            "target": {
                "moodle_site_id": "demo-moodle",
                "site_name": "Demo Moodle",
                "mode": "REST_API",
                "configured_mode": "REST_API",
            },
            "status": "PUBLISHED",
            "moodle_question_ref_id": "mock-demo-version",
            "request_payload": {
                "question_code": "Q-001",
                "export_format": "BOTH",
                "mock": True,
            },
            "response_payload": {
                "message": "Mô phỏng Moodle: chỉ ghi nhận publication cục bộ, chưa gửi dữ liệu sang Moodle thật.",
                "export_formats": ["gift", "xml"],
            },
        }

        item = _safe_publication_item(record)

        self.assertEqual(item["publication_mode"], "MOCK")
        self.assertEqual(item["configured_mode"], "REST_API")
        self.assertFalse(item["external_sync"])
        self.assertEqual(item["status_detail"], "SIMULATED_LOCAL_RECORD")
        self.assertEqual(item["status_label"], "Đã ghi mô phỏng")
        self.assertIn("chưa gửi", item["message"])

    def test_moodle_publish_is_idempotent_for_same_version_and_target(self):
        question_id = ObjectId()
        version_id = ObjectId()
        target_id = ObjectId()
        publisher_id = ObjectId()
        now = datetime.now(timezone.utc)

        class FakePublicationDatabase:
            def __init__(self):
                self.questions = InMemoryCollection(
                    [
                        {
                            "_id": question_id,
                            "schema_version": SCHEMA_VERSION,
                            "question_code": "Q-001",
                            "current_version": 1,
                            "current_version_id": version_id,
                            "approved_version_id": version_id,
                            "lifecycle_status": "ACTIVE",
                            "evaluation_status": "PASSED",
                            "review_status": "APPROVED",
                            "publication_status": "NOT_PUBLISHED",
                            "quality_summary": {},
                            "review_assignment": {"status": "UNASSIGNED"},
                            "latest_review_id": None,
                            "created_at": now,
                            "updated_at": now,
                        }
                    ]
                )
                self.question_versions = InMemoryCollection(
                    [
                        {
                            "_id": version_id,
                            "question_id": question_id,
                            "version": 1,
                            "document_id": None,
                            "content": "Queue xử lý phần tử theo nguyên tắc nào?",
                            "question_data": {
                                "options": {"A": "FIFO", "B": "LIFO"},
                                "correct_answer": "A",
                                "explanation": "Queue là hàng đợi FIFO.",
                            },
                            "classification": {"assessment_type": "TRAC_NGHIEM"},
                            "clos": [],
                            "sources": [],
                            "content_hash": "hash-v1",
                        }
                    ]
                )
                self.moodle_targets = InMemoryCollection(
                    [
                        {
                            "_id": target_id,
                            "site_key": "demo-moodle",
                            "site_name": "Demo Moodle",
                            "mode": "REST_API",
                            "default_course_id": "ctdl",
                            "default_category_id": "qbank",
                            "is_active": True,
                        }
                    ]
                )
                self.moodle_publications = InMemoryCollection()

        db = FakePublicationDatabase()
        original_transaction = question_workflow_module.mongo_transaction
        original_app_env = settings.app_env
        original_demo_mode = settings.demo_mode
        try:
            question_workflow_module.mongo_transaction = lambda: nullcontext(None)
            settings.app_env = "demo"
            settings.demo_mode = True
            service = QuestionWorkflowService(db)
            payload = MoodlePublicationRequest(expected_version=1)

            first = service.publish_to_moodle(str(question_id), payload, publisher_id)
            second = service.publish_to_moodle(str(question_id), payload, publisher_id)
        finally:
            question_workflow_module.mongo_transaction = original_transaction
            settings.app_env = original_app_env
            settings.demo_mode = original_demo_mode

        self.assertEqual(len(db.moodle_publications.records), 1)
        self.assertEqual(first["_id"], second["_id"])
        self.assertEqual(first["idempotency_key"], second["idempotency_key"])
        self.assertEqual(db.questions.find_one({"_id": question_id})["publication_status"], "PUBLISHED")
        publication = db.moodle_publications.records[0]
        self.assertEqual(publication["publication_mode"], "MOCK")
        self.assertFalse(publication["external_sync"])
        self.assertEqual(publication["status_detail"], "SIMULATED_LOCAL_RECORD")
        self.assertEqual(publication["target"]["configured_mode"], "REST_API")
        self.assertEqual(publication["target"]["course_id"], "ctdl")
        self.assertEqual(publication["target"]["category_id"], "qbank")
        self.assertIn("gift", publication["request_payload"]["exports"])
        self.assertIn("xml", publication["request_payload"]["exports"])
        self.assertIn("chưa gửi dữ liệu sang Moodle thật", publication["response_payload"]["message"])

    def test_moodle_target_payload_requires_real_api_config(self):
        with self.assertRaises(ValidationError):
            MoodleTargetPayload(
                site_key="ctu",
                site_name="CTU Moodle",
                mode="REST_API",
                default_course_id="ctdl",
                default_category_id="qbank",
            )

        payload = MoodleTargetPayload(
            site_key="ctu",
            site_name="CTU Moodle",
            mode="REST_API",
            base_url="https://moodle.example.edu/",
            token_env_var="MOODLE_TOKEN",
            default_course_id="ctdl",
            default_category_id="qbank",
        )
        self.assertEqual(payload.base_url, "https://moodle.example.edu")

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

    def test_exam_lifecycle_requires_exact_current_approved_questions(self):
        owner = _current_user("Teacher")
        exam = _exam_doc(owner.id)
        question_id = ObjectId()
        version_id = ObjectId()
        question = {
            "_id": question_id,
            "question_code": "Q-1",
            "current_version": 1,
            "current_version_id": version_id,
            "approved_version_id": version_id,
            "lifecycle_status": "ACTIVE",
            "evaluation_status": "PASSED",
            "review_status": "APPROVED",
            "publication_status": "NOT_PUBLISHED",
            "quality_summary": {},
            "review_assignment": {"status": "UNASSIGNED"},
            "latest_review_id": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        version = {
            "_id": version_id,
            "question_id": question_id,
            "document_id": None,
            "content": "Queue uses FIFO",
            "question_data": {"options": {"A": "FIFO"}, "correct_answer": "A"},
            "classification": {"subject": {"id": exam["subject_id"]}, "assessment_type": "TRAC_NGHIEM"},
            "clos": [],
            "sources": [],
            "content_hash": "hash",
        }
        service = ExamService(
            FakeExamRepository([exam]),
            FakeExamQuestionRepository([(question, version)]),
        )

        with self.assertRaises(ValueError):
            service.update_status(str(exam["_id"]), ExamStatusUpdateRequest(status="READY"), owner)

        exam["questions"] = [
            {
                "question_id": question_id,
                "version_id": version_id,
                "content_snapshot": {"content": "Queue uses FIFO"},
            }
        ]
        ready = service.update_status(
            str(exam["_id"]),
            ExamStatusUpdateRequest(status="READY"),
            owner,
        )
        result = service.update_status(
            str(exam["_id"]),
            ExamStatusUpdateRequest(status="FINALIZED"),
            owner,
        )

        self.assertEqual(ready["status"], "READY")
        self.assertEqual(result["status"], "FINALIZED")
        self.assertIn("finalized_snapshot", exam)

    def test_variant_creation_requires_finalized_exam(self):
        owner = _current_user("Teacher")
        exam = _exam_doc(owner.id)
        question_id = ObjectId()
        version_id = ObjectId()
        exam["questions"] = [
            {
                "question_id": question_id,
                "version_id": version_id,
                "content_snapshot": {
                    "content": "Queue uses FIFO",
                    "question_data": {"options": {"A": "FIFO"}, "correct_answer": "A"},
                },
            }
        ]
        exams = FakeExamRepository([exam])
        service = ExamVariantService(exams, FakeExamVariantRepository())

        with self.assertRaises(ValueError):
            service.create_variant(
                str(exam["_id"]),
                ExamVariantCreateRequest(exam_code="A01"),
                owner,
            )

        exam["status"] = "FINALIZED"
        exam["finalized_snapshot"] = {"questions": exam["questions"]}
        result = service.create_variant(
            str(exam["_id"]),
            ExamVariantCreateRequest(exam_code="A01"),
            owner,
        )
        self.assertEqual(result["exam_code"], "A01")

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

    def test_catalog_lifecycle_counts_usage_and_blocks_duplicate_codes(self):
        subject_id = ObjectId()
        other_subject_id = ObjectId()
        chapter_id = ObjectId()
        clo_id = ObjectId()
        version_id = ObjectId()
        subject = {
            "_id": subject_id,
            "subject_code": "CTDL",
            "subject_name": "Cấu trúc dữ liệu",
            "description": "",
            "is_active": True,
            "chapters": [
                {
                    "_id": chapter_id,
                    "chapter_code": "CH01",
                    "chapter_name": "Stack",
                    "sequence_no": 1,
                    "is_active": True,
                }
            ],
            "learning_outcomes": [
                {
                    "_id": clo_id,
                    "clo_code": "CLO1",
                    "description": "Hiểu cấu trúc dữ liệu tuyến tính",
                    "target_weight": 0.5,
                    "is_active": True,
                }
            ],
        }
        db = FakeCatalogDatabase(
            subjects=[
                subject,
                {
                    "_id": other_subject_id,
                    "subject_code": "MMT",
                    "subject_name": "Mạng máy tính",
                    "chapters": [],
                    "learning_outcomes": [],
                    "is_active": True,
                },
            ],
            documents=[{"subject_id": subject_id, "chapter_id": chapter_id, "archived_at": None}],
            question_versions=[
                {
                    "_id": version_id,
                    "classification": {
                        "subject": {"id": subject_id},
                        "chapter": {"id": chapter_id},
                    },
                    "clos": [{"id": clo_id}],
                }
            ],
            questions=[
                {
                    "schema_version": SCHEMA_VERSION,
                    "lifecycle_status": "ACTIVE",
                    "current_version_id": version_id,
                }
            ],
            exams=[{"subject_id": subject_id, "matrix": [{"chapter_id": chapter_id}]}],
        )
        service = CatalogService(db)

        result = service.list_subjects()[0]
        self.assertEqual(result["usage_counts"]["documents"], 1)
        self.assertEqual(result["usage_counts"]["questions"], 1)
        self.assertEqual(result["usage_counts"]["exams"], 1)
        self.assertEqual(result["chapters"][0]["usage_counts"]["documents"], 1)
        self.assertEqual(result["learning_outcomes"][0]["usage_counts"]["questions"], 1)

        with self.assertRaises(ValueError):
            service.add_chapter(
                str(subject_id),
                ChapterPayload(chapter_code="CH01", chapter_name="Duplicate"),
            )
        with self.assertRaises(ValueError):
            service.add_learning_outcome(
                str(subject_id),
                LearningOutcomePayload(clo_code="CLO1", description="Duplicate"),
            )
        with self.assertRaises(ValueError):
            service.update_subject(
                str(subject_id),
                SubjectUpdatePayload(subject_code="MMT"),
            )

        updated = service.update_chapter(
            str(subject_id),
            str(chapter_id),
            ChapterUpdatePayload(chapter_code="CH02", is_active=False),
        )
        self.assertEqual(updated["chapters"][0]["chapter_code"], "CH02")
        self.assertFalse(updated["chapters"][0]["is_active"])

        updated = service.update_learning_outcome(
            str(subject_id),
            str(clo_id),
            LearningOutcomeUpdatePayload(target_weight=0.75, is_active=False),
        )
        self.assertEqual(updated["learning_outcomes"][0]["target_weight"], 0.75)
        self.assertFalse(updated["learning_outcomes"][0]["is_active"])

    def test_catalog_runtime_controls_prompt_policy_and_model_state(self):
        db = FakeCatalogDatabase(
            ai_models=[
                {
                    "_id": ObjectId(),
                    "model_code": "qwen",
                    "model_name": "Qwen local",
                    "runtime": "OLLAMA",
                    "kind": "CHAT",
                    "revision": "local",
                    "capabilities": ["QUESTION_GENERATION"],
                    "priority": 1,
                    "is_local": True,
                    "is_active": True,
                    "config": {},
                },
                {
                    "_id": ObjectId(),
                    "model_code": "unknown-provider",
                    "model_name": "Unknown",
                    "runtime": "CUSTOM",
                    "kind": "CHAT",
                    "revision": "local",
                    "capabilities": [],
                    "priority": 2,
                    "is_local": True,
                    "is_active": True,
                    "config": {},
                },
            ],
            prompt_templates=[
                {
                    "_id": ObjectId(),
                    "template_key": "system",
                    "version": 1,
                    "kind": "SYSTEM",
                    "name": "System v1",
                    "prompt_body": "v1",
                    "is_active": False,
                },
                {
                    "_id": ObjectId(),
                    "template_key": "system",
                    "version": 2,
                    "kind": "SYSTEM",
                    "name": "System v2",
                    "prompt_body": "v2",
                    "is_active": True,
                },
            ],
            evaluation_policies=[
                {
                    "_id": ObjectId(),
                    "policy_name": "Default",
                    "version": 1,
                    "weights": {"faithfulness": 1},
                    "thresholds": {"pass_min": 0.7},
                    "is_active": False,
                },
                {
                    "_id": ObjectId(),
                    "policy_name": "Default",
                    "version": 2,
                    "weights": {"faithfulness": 1},
                    "thresholds": {"pass_min": 0.8},
                    "is_active": True,
                },
            ],
        )
        service = CatalogService(db)

        models = service.list_ai_models()
        self.assertTrue(models[0]["factory_status"]["supported"])
        self.assertFalse(models[1]["factory_status"]["supported"])

        model = service.set_ai_model_active(
            AiModelActivationPayload(model_code="qwen", is_active=False)
        )
        self.assertFalse(model["is_active"])

        prompt = service.activate_prompt_template(
            PromptTemplateActivationPayload(template_key="system", version=1)
        )
        self.assertTrue(prompt["is_active"])
        self.assertFalse(db.prompt_templates.find_one({"template_key": "system", "version": 2})["is_active"])

        policy = service.activate_evaluation_policy(
            EvaluationPolicyActivationPayload(policy_name="Default", version=1)
        )
        self.assertTrue(policy["is_active"])
        self.assertFalse(db.evaluation_policies.find_one({"policy_name": "Default", "version": 2})["is_active"])

        runtime = service.runtime_config()
        self.assertIn("prompt_source", runtime)
        self.assertIn("supported_provider_patterns", runtime)

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

    def test_admin_overview_summarizes_operational_state(self):
        now = datetime.now(timezone.utc)
        old = now - timedelta(minutes=settings.job_recovery_timeout_minutes + 5)

        class FakeOverviewDatabase:
            def __init__(self):
                self.users = InMemoryCollection(
                    [
                        {"_id": ObjectId(), "role": "Admin", "is_active": True},
                        {"_id": ObjectId(), "role": "Teacher", "is_active": True},
                        {"_id": ObjectId(), "role": "Reviewer", "is_active": True},
                        {"_id": ObjectId(), "role": "Teacher", "is_active": False},
                    ]
                )
                self.questions = InMemoryCollection(
                    [
                        {
                            "_id": ObjectId(),
                            "lifecycle_status": "ACTIVE",
                            "review_status": "PENDING",
                            "publication_status": "NOT_PUBLISHED",
                        },
                        {
                            "_id": ObjectId(),
                            "lifecycle_status": "ACTIVE",
                            "review_status": "APPROVED",
                            "publication_status": "PUBLISHED",
                        },
                        {
                            "_id": ObjectId(),
                            "lifecycle_status": "ARCHIVED",
                            "review_status": "PENDING",
                            "publication_status": "NOT_PUBLISHED",
                        },
                    ]
                )
                self.documents = InMemoryCollection(
                    [
                        {"_id": ObjectId(), "archived_at": None, "status": "PROCESSING"},
                        {"_id": ObjectId(), "archived_at": None, "status": "FAILED"},
                        {"_id": ObjectId(), "archived_at": now, "status": "FAILED"},
                    ]
                )
                self.generation_jobs = InMemoryCollection(
                    [
                        {
                            "_id": ObjectId(),
                            "status": "failed",
                            "request": {"document_id": "doc-1"},
                            "error_message": "Model timeout",
                            "created_at": old,
                            "updated_at": old,
                        },
                        {
                            "_id": ObjectId(),
                            "status": "processing",
                            "request": {"document_id": "doc-2"},
                            "error_message": None,
                            "created_at": old,
                            "updated_at": old,
                        },
                    ]
                )
                self.evaluation_jobs = InMemoryCollection()
                self.document_jobs = InMemoryCollection()
                self.moodle_targets = InMemoryCollection(
                    [
                        {"_id": ObjectId(), "site_key": "demo", "is_active": True},
                        {"_id": ObjectId(), "site_key": "old", "is_active": False},
                    ]
                )
                self.moodle_publications = InMemoryCollection(
                    [
                        {
                            "_id": ObjectId(),
                            "status": "PUBLISHED",
                            "publication_mode": "MOCK",
                            "request_payload": {"mock": True},
                        },
                        {"_id": ObjectId(), "status": "FAILED", "request_payload": {"mock": True}},
                    ]
                )
                self.audit_logs = InMemoryCollection(
                    [
                        {
                            "_id": ObjectId(),
                            "action": "admin.job_retry",
                            "actor_user_id": str(ObjectId()),
                            "entity_type": "job",
                            "entity_id": "job-1",
                            "created_at": now,
                        }
                    ]
                )

        overview = AdminOverviewService(FakeOverviewDatabase()).overview()

        self.assertEqual(overview["users"]["active"], 3)
        self.assertEqual(overview["questions"]["pending"], 1)
        self.assertEqual(overview["questions"]["published"], 1)
        self.assertEqual(overview["documents"]["failed"], 1)
        self.assertEqual(overview["jobs"]["failed"], 1)
        self.assertEqual(overview["jobs"]["long_running"], 1)
        self.assertEqual(overview["moodle"]["active_targets"], 1)
        self.assertEqual(overview["moodle"]["publications"]["simulated"], 2)
        self.assertEqual(overview["recent_jobs"][0]["error_message"], "Model timeout")
        self.assertEqual(overview["recent_audit"][0]["action"], "admin.job_retry")
        attention = {item["key"]: item for item in overview["attention"]}
        self.assertEqual(attention["retryable_jobs"]["severity"], "danger")
        self.assertEqual(attention["failed_documents"]["count"], 1)

    def test_job_recovery_marks_only_stale_active_jobs(self):
        now = datetime.now(timezone.utc)
        old = now - timedelta(minutes=180)
        fresh = now - timedelta(minutes=5)
        question_id = ObjectId()
        evaluation_job_id = ObjectId()
        document_id = ObjectId()
        chunk_job_id = ObjectId()
        chunk_set_id = ObjectId()
        fresh_generation_id = ObjectId()

        class FakeRecoveryDatabase:
            def __init__(self):
                self.generation_jobs = InMemoryCollection(
                    [
                        {"_id": ObjectId(), "status": "queued", "updated_at": old},
                        {"_id": fresh_generation_id, "status": "processing", "updated_at": fresh},
                    ]
                )
                self.evaluation_jobs = InMemoryCollection(
                    [
                        {
                            "_id": evaluation_job_id,
                            "status": "PROCESSING",
                            "question_id": question_id,
                            "updated_at": old,
                        }
                    ]
                )
                self.questions = InMemoryCollection(
                    [
                        {
                            "_id": question_id,
                            "evaluation_status": "PROCESSING",
                            "quality_summary": {"latest_evaluation_job_id": evaluation_job_id},
                        }
                    ]
                )
                self.document_jobs = InMemoryCollection(
                    [
                        {
                            "_id": chunk_job_id,
                            "document_id": document_id,
                            "job_type": "CHUNK",
                            "status": "PROCESSING",
                            "updated_at": old,
                        }
                    ]
                )
                self.documents = InMemoryCollection(
                    [
                        {
                            "_id": document_id,
                            "archived_at": None,
                            "status": "PROCESSING",
                            "pipeline_summary": {"chunk_status": "PROCESSING"},
                        }
                    ]
                )
                self.chunk_sets = InMemoryCollection(
                    [{"_id": chunk_set_id, "chunk_job_id": chunk_job_id, "status": "PROCESSING"}]
                )
                self.chunk_embeddings = InMemoryCollection(
                    [{"_id": ObjectId(), "chunk_set_id": chunk_set_id, "status": "PENDING"}]
                )

        db = FakeRecoveryDatabase()
        original_get_database = job_recovery.get_database
        try:
            job_recovery.get_database = lambda: db
            result = job_recovery.recover_stale_jobs(timeout_minutes=60)
        finally:
            job_recovery.get_database = original_get_database

        self.assertEqual(
            result,
            {"generation_failed": 1, "evaluation_stale": 1, "document_failed": 1},
        )
        self.assertEqual(db.generation_jobs.find_one({"_id": fresh_generation_id})["status"], "processing")
        self.assertEqual(db.evaluation_jobs.find_one({"_id": evaluation_job_id})["status"], "STALE")
        question = db.questions.find_one({"_id": question_id})
        self.assertEqual(question["evaluation_status"], "STALE")
        self.assertIn("exceeded 60 minute recovery timeout", question["quality_summary"]["error"]["message"])
        document = db.documents.find_one({"_id": document_id})
        self.assertEqual(document["status"], "FAILED")
        self.assertEqual(document["pipeline_summary"]["chunk_status"], "FAILED")
        self.assertEqual(db.chunk_sets.find_one({"_id": chunk_set_id})["status"], "FAILED")
        self.assertEqual(db.chunk_embeddings.find_one({"chunk_set_id": chunk_set_id})["status"], "FAILED")

    def test_admin_audit_service_normalizes_flat_and_nested_records(self):
        class FakeCursor(list):
            def sort(self, *_args):
                return self

            def skip(self, *_args):
                return self

            def limit(self, *_args):
                return self

        class FakeAuditLogs:
            def __init__(self, records):
                self.records = records
                self.match = None

            def count_documents(self, match):
                self.match = match
                return len(self.records)

            def find(self, match):
                self.match = match
                return FakeCursor(self.records)

        class FakeDatabase:
            def __init__(self, records):
                self.audit_logs = FakeAuditLogs(records)

        now = datetime.now(timezone.utc)
        actor_id = ObjectId()
        question_id = ObjectId()
        review_id = ObjectId()
        records = [
            {
                "_id": ObjectId(),
                "action": "user.admin_update",
                "actor_user_id": str(actor_id),
                "actor_role": "Admin",
                "entity_type": "user",
                "entity_id": "user-1",
                "before": {"role": "Teacher"},
                "after": {"role": "Reviewer"},
                "created_at": now,
            },
            {
                "_id": ObjectId(),
                "action": "QUESTION_APPROVED",
                "actor": {"type": "USER", "user_id": actor_id},
                "entity": {"type": "QUESTION", "id": question_id, "version_id": ObjectId()},
                "changes": [{"path": "review_status", "old_value": "PENDING", "new_value": "APPROVED"}],
                "metadata": {"review_id": review_id},
                "created_at": now,
            },
        ]
        db = FakeDatabase(records)
        service = AdminAuditService(db)

        result = service.list(
            page=1,
            page_size=10,
            actor_user_id=str(actor_id),
            entity_type="question",
            entity_id=str(question_id),
            action="QUESTION_APPROVED",
            search="approved",
        )

        self.assertEqual(result["total"], 2)
        self.assertIn("$and", db.audit_logs.match)
        self.assertEqual(result["items"][0]["actor"]["role"], "Admin")
        self.assertEqual(result["items"][0]["before"], {"role": "Teacher"})
        self.assertEqual(result["items"][1]["actor"]["user_id"], str(actor_id))
        self.assertEqual(result["items"][1]["entity"]["id"], str(question_id))
        self.assertEqual(result["items"][1]["metadata"]["review_id"], str(review_id))

    def test_reviewer_dashboard_summarizes_workload_and_reviews(self):
        def get_path(record, path):
            current = record
            for part in path.split("."):
                if not isinstance(current, dict) or part not in current:
                    return None
                current = current[part]
            return current

        def matches(record, match):
            if "$and" in match:
                return all(matches(record, clause) for clause in match["$and"])
            if "$or" in match:
                return any(matches(record, clause) for clause in match["$or"])
            for key, expected in match.items():
                actual = get_path(record, key)
                if isinstance(expected, dict):
                    if "$exists" in expected and (actual is not None) != expected["$exists"]:
                        return False
                    if "$in" in expected and actual not in expected["$in"]:
                        return False
                    if "$gte" in expected and (actual is None or actual < expected["$gte"]):
                        return False
                    if "$lte" in expected and (actual is None or actual > expected["$lte"]):
                        return False
                    continue
                if actual != expected:
                    return False
            return True

        class FakeCursor(list):
            def sort(self, *_args):
                return self

            def limit(self, count):
                return FakeCursor(self[:count])

        class FakeCollection:
            def __init__(self, records):
                self.records = records

            def count_documents(self, match):
                return sum(1 for record in self.records if matches(record, match))

            def find(self, match=None, *_args):
                match = match or {}
                return FakeCursor([record for record in self.records if matches(record, match)])

        class FakeDatabase:
            def __init__(self, **collections):
                for name, records in collections.items():
                    setattr(self, name, FakeCollection(records))

        now = datetime.now(timezone.utc)
        reviewer_id = ObjectId()
        other_reviewer_id = ObjectId()
        subject_id = ObjectId()
        version_ids = [ObjectId(), ObjectId()]
        base_question = {
            "schema_version": SCHEMA_VERSION,
            "lifecycle_status": "ACTIVE",
            "review_status": "PENDING",
        }
        db = FakeDatabase(
            questions=[
                {**base_question, "_id": ObjectId(), "review_assignment": {"status": "UNASSIGNED"}},
                {
                    **base_question,
                    "_id": ObjectId(),
                    "review_assignment": {"status": "ASSIGNED", "reviewer_user_id": reviewer_id},
                },
                {
                    **base_question,
                    "_id": ObjectId(),
                    "review_assignment": {
                        "status": "IN_REVIEW",
                        "reviewer_user_id": reviewer_id,
                        "lock_expires_at": now - timedelta(minutes=5),
                    },
                },
                {
                    **base_question,
                    "_id": ObjectId(),
                    "review_assignment": {
                        "status": "IN_REVIEW",
                        "reviewer_user_id": other_reviewer_id,
                        "lock_expires_at": now + timedelta(minutes=30),
                    },
                },
            ],
            question_reviews=[
                {
                    "_id": ObjectId(),
                    "question_version_id": version_ids[0],
                    "reviewer_user_id": reviewer_id,
                    "decision": "APPROVED",
                    "override": {"applied": True},
                    "revision_issues": [],
                    "reviewed_at": now - timedelta(days=1),
                },
                {
                    "_id": ObjectId(),
                    "question_version_id": version_ids[1],
                    "reviewer_user_id": reviewer_id,
                    "decision": "NEEDS_REVISION",
                    "override": {"applied": False},
                    "revision_issues": [{"title": "Sửa đáp án"}],
                    "reviewed_at": now - timedelta(days=2),
                },
            ],
            audit_logs=[
                {
                    "action": "QUESTION_APPROVED",
                    "actor": {"user_id": reviewer_id},
                    "metadata": {"review_assignment": {"claimed_at": now - timedelta(hours=2)}},
                    "created_at": now,
                },
                {
                    "action": "QUESTION_NEEDS_REVISION",
                    "actor": {"user_id": reviewer_id},
                    "metadata": {"review_assignment": {"assigned_at": now - timedelta(hours=4)}},
                    "created_at": now,
                },
            ],
            question_versions=[
                {"_id": version_ids[0], "classification": {"subject": {"id": subject_id}}},
                {"_id": version_ids[1], "classification": {"subject": {"id": subject_id}}},
            ],
            subjects=[
                {"_id": subject_id, "subject_code": "CTDL", "subject_name": "Cấu trúc dữ liệu"},
            ],
        )
        dashboard = QuestionWorkflowService(db).review_dashboard(_current_user("Reviewer", reviewer_id))

        self.assertEqual(dashboard["workload"]["pending"], 4)
        self.assertEqual(dashboard["workload"]["unassigned"], 1)
        self.assertEqual(dashboard["workload"]["assigned"], 1)
        self.assertEqual(dashboard["workload"]["in_review"], 2)
        self.assertEqual(dashboard["workload"]["lock_expired"], 1)
        self.assertEqual(dashboard["workload"]["mine"], 2)
        self.assertEqual(dashboard["performance"]["reviews_30d"], 2)
        self.assertEqual(dashboard["performance"]["approval_rate"], 0.5)
        self.assertEqual(dashboard["performance"]["override_count"], 1)
        self.assertEqual(dashboard["performance"]["revision_issues"], 1)
        self.assertEqual(dashboard["performance"]["average_review_hours"], 3.0)
        self.assertEqual(dashboard["subjects"][0]["label"], "CTDL")
        self.assertEqual(dashboard["subjects"][0]["reviewed"], 2)

    def test_notification_service_creates_and_marks_read(self):
        class FakeCursor(list):
            def sort(self, *_args):
                return self

            def skip(self, count):
                return FakeCursor(self[count:])

            def limit(self, count):
                return FakeCursor(self[:count])

        class FakeUpdateResult:
            def __init__(self, modified_count):
                self.modified_count = modified_count

        class FakeNotifications:
            def __init__(self):
                self.records = []

            @staticmethod
            def _matches(record, query):
                return all(record.get(key) == value for key, value in query.items())

            def insert_one(self, record):
                self.records.append(record)

            def count_documents(self, query):
                return sum(1 for record in self.records if self._matches(record, query))

            def find(self, query):
                return FakeCursor([record for record in self.records if self._matches(record, query)])

            def find_one_and_update(self, query, update, return_document=None):
                for record in self.records:
                    if self._matches(record, query):
                        record.update(update.get("$set", {}))
                        return record
                return None

            def update_many(self, query, update):
                modified = 0
                for record in self.records:
                    if self._matches(record, query):
                        record.update(update.get("$set", {}))
                        modified += 1
                return FakeUpdateResult(modified)

        class FakeDatabase:
            def __init__(self):
                self.notifications = FakeNotifications()

        db = FakeDatabase()
        service = NotificationService(db)
        teacher = _current_user("Teacher")
        reviewer = _current_user("Reviewer")
        question_id = ObjectId()
        version_id = ObjectId()
        notification = service.notify_review_decision(
            question={
                "_id": question_id,
                "question_code": "Q-1",
                "created_by_user_id": teacher.id,
            },
            version={"_id": version_id, "created_by_user_id": teacher.id},
            review={"decision": "NEEDS_REVISION", "note": "Cần sửa đáp án"},
            actor_user_id=reviewer.id,
        )

        self.assertIsNotNone(notification)
        self.assertEqual(notification["type"], "QUESTION_NEEDS_REVISION")
        self.assertEqual(notification["entity"]["id"], str(question_id))
        self.assertEqual(service.unread_count(teacher), 1)
        page = service.list(teacher, 1, 10)
        self.assertEqual(page["total"], 1)
        self.assertFalse(page["items"][0]["is_read"])

        marked = service.mark_read(notification["id"], teacher)
        self.assertTrue(marked["is_read"])
        self.assertEqual(service.unread_count(teacher), 0)

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
        for collection in ("users", "documents", "questions", "question_versions", "evaluation_jobs", "moodle_targets"):
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

    def test_question_validator_allows_review_assignment_state(self):
        question_properties = VALIDATORS["questions"]["$jsonSchema"]["properties"]
        self.assertEqual(question_properties["review_assignment"]["bsonType"], "object")

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
        subject_id = ObjectId()
        chapter_id = ObjectId()
        clo_id = ObjectId()
        reviewer_id = ObjectId()

        pairs, total = repo.list(
            2,
            10,
            "PENDING",
            "queue",
            question_type="trac_nghiem",
            bloom_level=3,
            document_id=str(document_id),
            subject_id=str(subject_id),
            chapter_id=str(chapter_id),
            clo_id=str(clo_id),
            difficulty="kho",
            quality_color="green",
            min_score=0.8,
            publication_status="NOT_PUBLISHED",
            evaluation_status="PASSED",
            assignment_status="IN_REVIEW",
            assigned_reviewer_user_id=reviewer_id,
        )

        self.assertEqual(pairs, [])
        self.assertEqual(total, 0)
        pipeline = fake_db.questions.pipeline
        self.assertIsNotNone(pipeline)
        question_match = pipeline[0]["$match"]
        self.assertEqual(question_match["review_status"], "PENDING")
        self.assertEqual(question_match["publication_status"], "NOT_PUBLISHED")
        self.assertEqual(question_match["evaluation_status"], "PASSED")
        self.assertEqual(question_match["review_assignment.status"], "IN_REVIEW")
        self.assertEqual(question_match["review_assignment.reviewer_user_id"], reviewer_id)
        self.assertEqual(question_match["quality_summary.color"], "GREEN")
        self.assertEqual(question_match["quality_summary.overall_score"], {"$gte": 0.8})

        version_match = pipeline[3]["$match"]
        self.assertEqual(version_match["version.classification.assessment_type"], "TRAC_NGHIEM")
        self.assertEqual(version_match["version.classification.bloom.level"], 3)
        self.assertEqual(version_match["version.document_id"], document_id)
        self.assertEqual(version_match["version.classification.subject.id"], subject_id)
        self.assertEqual(version_match["version.classification.chapter.id"], chapter_id)
        self.assertEqual(version_match["version.clos.id"], clo_id)
        self.assertEqual(version_match["version.classification.difficulty"], "kho")

        search_match = pipeline[4]["$match"]
        self.assertIn({"question_code": {"$regex": "queue", "$options": "i"}}, search_match["$or"])
        self.assertIn({"version.content": {"$regex": "queue", "$options": "i"}}, search_match["$or"])
        facet = pipeline[-1]["$facet"]
        self.assertEqual(facet["items"][0], {"$skip": 10})
        self.assertEqual(facet["items"][1], {"$limit": 10})


if __name__ == "__main__":
    unittest.main()
