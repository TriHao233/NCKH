from __future__ import annotations

import hashlib
import json
import random
import re
from copy import deepcopy
from typing import Any

from bson import ObjectId

from core.bootstrap import SCHEMA_VERSION
from core.access_policy import has_subject_access
from core.access_policy import active_subject_ids
from core.database import get_database
from core.dependencies import CurrentUser
from modules.exams.repository import (
    ExamRepository,
    ExamVariantRepository,
    MongoExamRepository,
    MongoExamVariantRepository,
    json_safe,
    object_id,
    utc_now,
)
from modules.exams.schemas import (
    MAX_VARIANTS_PER_EXAM,
    COGNITIVE_LEVEL_TO_BLOOM,
    AddQuestionsManualRequest,
    ExamCreateRequest,
    ExamMatrixRequest,
    ExamStatus,
    ExamStatusUpdateRequest,
    ExamUpdateRequest,
    ExamVariantCreateRequest,
    MatrixCell,
)
from modules.questions.repository import MongoQuestionRepository, serialize_question

APPROVED_STATUS = "APPROVED"
EDITABLE_EXAM_STATUSES = {"DRAFT", "READY"}
LOCKED_EXAM_STATUSES = {"FINALIZED", "ARCHIVED"}
STATUS_ALIASES = {
    "draft": "DRAFT",
    "ready": "READY",
    "finalized": "FINALIZED",
    "archived": "ARCHIVED",
}


def _exam_status(exam: dict) -> str:
    raw_status = str(exam.get("status") or "DRAFT")
    return STATUS_ALIASES.get(raw_status, raw_status.upper())


def _matrix_cell_dict(cell: MatrixCell) -> dict:
    return {
        "chapter_id": object_id(cell.chapter_id, "chapter_id") if cell.chapter_id else None,
        "cognitive_level": cell.cognitive_level.value if cell.cognitive_level else None,
        "bloom_levels": cell.bloom_levels,
        "clo_ids": [object_id(value, "clo_id") for value in cell.clo_ids],
        "question_types": cell.question_types,
        "difficulty": cell.difficulty.value,
        "count": cell.count,
        "marks_per_question": cell.marks_per_question,
    }


def serialize_exam(exam: dict, variant_count: int = 0) -> dict:
    return json_safe(
        {
            "id": exam["_id"],
            "name": exam["name"],
            "exam_title": exam["exam_title"],
            "subject_id": exam["subject_id"],
            "question_count": exam["question_count"],
            "header": exam["header"],
            "matrix": exam.get("matrix", []),
            "questions": exam.get("questions", []),
            "status": _exam_status(exam),
            "variant_count": variant_count,
            "delivery_mode": exam.get("delivery_mode", "paper"),
            "time_limit_seconds": exam.get("time_limit_seconds"),
            "scoring_config": exam.get("scoring_config"),
            "lms_export_status": exam.get("lms_export_status", "not_exported"),
            "blueprint_version": exam.get("blueprint_version", 1),
            "total_marks": exam.get("total_marks", 0),
            "selection_seed": exam.get("selection_seed"),
            "coverage_report": exam.get("coverage_report"),
            "eligibility_manifest": exam.get("eligibility_manifest"),
            "revision": exam.get("revision", 1),
            "finalized_at": exam.get("finalized_at"),
            "created_by_user_id": exam.get("created_by_user_id"),
            "created_at": exam["created_at"],
            "updated_at": exam["updated_at"],
        }
    )


def serialize_variant(variant: dict) -> dict:
    return json_safe(
        {
            "id": variant["_id"],
            "exam_id": variant["exam_id"],
            "exam_code": variant["exam_code"],
            "questions": variant["questions"],
            "answer_key": variant["answer_key"],
            "seed": variant.get("seed", ""),
            "exam_revision": variant.get("exam_revision", 1),
            "permutation": variant.get("permutation", []),
            "export_manifest": variant.get("export_manifest", {}),
            "created_at": variant["created_at"],
        }
    )


class ExamService:
    def __init__(self, repository: ExamRepository, question_repository: MongoQuestionRepository):
        self.repository = repository
        self.question_repository = question_repository

    def _get_or_404(self, exam_id: str) -> dict:
        exam = self.repository.find(exam_id)
        if not exam:
            raise LookupError("Không tìm thấy đề thi")
        return exam

    @staticmethod
    def _assert_can_access(
        exam: dict,
        current_user: CurrentUser | None,
        repository: ExamRepository | None = None,
    ) -> None:
        if current_user is None:
            raise PermissionError("Bạn chưa đăng nhập")
        if current_user.role == "Admin":
            return
        if current_user.role == "Teacher" and str(exam.get("created_by_user_id")) == str(current_user.id):
            access_database = getattr(repository, "db", None)
            if getattr(access_database, "subject_memberships", None) is None or has_subject_access(
                access_database, current_user.id, exam.get("subject_id")
            ):
                return
        raise PermissionError("Bạn không có quyền truy cập đề thi này")

    def _get_for_user_or_404(self, exam_id: str, current_user: CurrentUser | None) -> dict:
        exam = self._get_or_404(exam_id)
        self._assert_can_access(exam, current_user, self.repository)
        return exam

    @staticmethod
    def _assert_mutable(exam: dict) -> None:
        if _exam_status(exam) in LOCKED_EXAM_STATUSES:
            raise ValueError("Đề thi đã chốt hoặc lưu trữ, không thể chỉnh sửa nội dung")

    @staticmethod
    def _question_subject_id(version: dict) -> str | None:
        subject = (version.get("classification") or {}).get("subject") or {}
        subject_id = subject.get("id") if isinstance(subject, dict) else subject
        return str(subject_id) if subject_id else None

    def _assert_question_can_join_exam(self, exam: dict, question: dict, version: dict) -> None:
        if question.get("review_status") != APPROVED_STATUS:
            raise ValueError(f"Câu hỏi {question.get('question_code')} chưa được duyệt")
        if str(question.get("current_version_id")) != str(version["_id"]):
            raise ValueError(f"Câu hỏi {question.get('question_code')} đã có version mới hơn")
        if str(question.get("approved_version_id")) != str(version["_id"]):
            raise ValueError(f"Câu hỏi {question.get('question_code')} chưa chốt version đã duyệt")
        question_subject_id = self._question_subject_id(version)
        if not question_subject_id or question_subject_id != str(exam["subject_id"]):
            raise ValueError(f"Câu hỏi {question.get('question_code')} không thuộc môn của đề thi")

    def _is_question_usable_for_exam(self, exam: dict, question: dict, version: dict) -> bool:
        try:
            self._assert_question_can_join_exam(exam, question, version)
        except ValueError:
            return False
        return True

    @staticmethod
    def _cell_blooms(cell: dict) -> set[int]:
        values = cell.get("bloom_levels") or []
        if not values and cell.get("cognitive_level"):
            values = COGNITIVE_LEVEL_TO_BLOOM.get(cell["cognitive_level"], set())
        return {int(value) for value in values}

    @classmethod
    def _matches_cell(cls, version: dict, cell: dict) -> bool:
        classification = version.get("classification") or {}
        bloom = (classification.get("bloom") or {}).get("level")
        chapter = (classification.get("chapter") or {}).get("id")
        qtype = str(classification.get("assessment_type") or "").lower()
        clos = {str(item.get("id") or item) for item in version.get("clos", [])}
        return (
            (not cls._cell_blooms(cell) or bloom in cls._cell_blooms(cell))
            and (not cell.get("chapter_id") or str(chapter) == str(cell["chapter_id"]))
            and (not cell.get("clo_ids") or bool(clos & {str(value) for value in cell["clo_ids"]}))
            and (not cell.get("question_types") or qtype in {str(value).lower() for value in cell["question_types"]})
            and (not cell.get("difficulty") or classification.get("difficulty") == cell["difficulty"])
        )

    def _eligible_pairs(self, exam: dict, current_user: CurrentUser) -> list[tuple[dict, dict]]:
        visible_subjects = (
            active_subject_ids(getattr(self.question_repository, "db", None), current_user.id)
            if current_user.role != "Admin"
            else ()
        )
        pairs, _total = self.question_repository.list(
            1,
            100000,
            APPROVED_STATUS,
            None,
            subject_id=str(exam["subject_id"]),
            visible_to_user_id=current_user.id if current_user.role != "Admin" else None,
            visible_subject_ids=visible_subjects,
            approved_current_only=True,
            sort_by="updated",
        )
        return [pair for pair in pairs if self._is_question_usable_for_exam(exam, *pair)]

    def _allocate(self, exam: dict, pairs: list[tuple[dict, dict]], seed: str) -> tuple[list[tuple[dict, dict]], dict]:
        cells = exam.get("matrix", [])
        candidate_rows = [[pair for pair in pairs if self._matches_cell(pair[1], cell)] for cell in cells]
        shortages = [
            {
                "cell_index": index,
                "requested": int(cell["count"]),
                "available": len(candidate_rows[index]),
                "shortage": max(0, int(cell["count"]) - len(candidate_rows[index])),
            }
            for index, cell in enumerate(cells)
            if len(candidate_rows[index]) < int(cell["count"])
        ]
        if shortages:
            return [], {"valid": False, "shortages": shortages, "assignments": []}

        slots = [index for index, cell in enumerate(cells) for _ in range(int(cell["count"]))]
        slots.sort(key=lambda index: len(candidate_rows[index]))
        chosen: list[tuple[int, tuple[dict, dict]]] = []
        used: set[str] = set()
        explored = 0
        max_explored = 100000

        def ranked(index: int):
            return sorted(
                candidate_rows[index],
                key=lambda pair: hashlib.sha256(f"{seed}:{pair[0]['_id']}:{index}".encode()).hexdigest(),
            )

        def solve(position: int) -> bool:
            nonlocal explored
            explored += 1
            if explored > max_explored:
                return False
            if position == len(slots):
                return True
            cell_index = slots[position]
            for pair in ranked(cell_index):
                question_id = str(pair[0]["_id"])
                if question_id in used:
                    continue
                used.add(question_id)
                chosen.append((cell_index, pair))
                if solve(position + 1):
                    return True
                chosen.pop()
                used.remove(question_id)
            return False

        if not solve(0):
            return [], {
                "valid": False,
                "shortages": [],
                "conflict": "Các ô blueprint chồng lấn và không thể cấp phát mỗi câu đúng một lần",
                "solver_limit_reached": explored > max_explored,
                "assignments": [],
            }
        chosen.sort(key=lambda item: (item[0], str(item[1][0]["_id"])))
        assignments = [{"cell_index": cell_index, "question_id": str(pair[0]["_id"])} for cell_index, pair in chosen]
        return [pair for _, pair in chosen], {
            "valid": True,
            "shortages": [],
            "assignments": assignments,
            "selected_count": len(chosen),
        }

    def _validate_ready_payload(self, exam: dict) -> None:
        questions = exam.get("questions", [])
        if len(questions) != int(exam["question_count"]):
            raise ValueError(f"Đề thi cần đúng {exam['question_count']} câu trước khi chốt")
        matrix_total = sum(int(cell.get("count", 0)) for cell in exam.get("matrix", []))
        if exam.get("matrix") and matrix_total != int(exam["question_count"]):
            raise ValueError("Tổng số câu trong ma trận phải bằng số câu của đề thi")
        selected_pairs = []
        for ref in questions:
            pair = self.question_repository.find_pair(str(ref["question_id"]))
            if not pair:
                raise ValueError("Một câu hỏi trong đề không còn tồn tại")
            question, version = pair
            if str(ref.get("version_id")) != str(version["_id"]):
                raise ValueError(f"Câu hỏi {question.get('question_code')} không còn ở version đã chọn")
            self._assert_question_can_join_exam(exam, question, version)
            selected_pairs.append((question, version))
        if exam.get("matrix"):
            _allocated, report = self._allocate(exam, selected_pairs, "coverage-validation")
            if not report["valid"]:
                raise ValueError(
                    "Câu hỏi đã chọn không phủ đúng blueprint: " + json.dumps(json_safe(report), ensure_ascii=False)
                )

    @staticmethod
    def _finalized_snapshot(exam: dict) -> dict:
        snapshot = {
            "subject_id": exam["subject_id"],
            "question_count": exam["question_count"],
            "header": exam["header"],
            "matrix": exam.get("matrix", []),
            "questions": exam.get("questions", []),
            "blueprint_version": exam.get("blueprint_version", 2),
            "total_marks": exam.get("total_marks", 0),
            "selection_seed": exam.get("selection_seed"),
            "coverage_report": exam.get("coverage_report"),
            "eligibility_manifest": exam.get("eligibility_manifest"),
            "revision": int(exam.get("revision", 1)) + 1,
            "created_at": utc_now(),
        }
        digest_payload = json.dumps(json_safe(snapshot), ensure_ascii=False, sort_keys=True, default=str)
        snapshot["sha256"] = hashlib.sha256(digest_payload.encode()).hexdigest()
        return deepcopy(snapshot)

    def create_exam(self, payload: ExamCreateRequest, current_user: CurrentUser | ObjectId) -> dict:
        now = utc_now()
        created_by_user_id = current_user.id if isinstance(current_user, CurrentUser) else current_user
        subject_id = object_id(payload.subject_id, "subject_id")
        access_database = getattr(self.repository, "db", None)
        if (
            isinstance(current_user, CurrentUser)
            and current_user.role != "Admin"
            and getattr(access_database, "subject_memberships", None) is not None
            and not has_subject_access(access_database, current_user.id, subject_id)
        ):
            raise PermissionError("Bạn chưa được phân công vào học phần đã chọn")
        exam = {
            "_id": ObjectId(),
            "schema_version": SCHEMA_VERSION,
            "name": payload.name,
            "exam_title": payload.exam_title,
            "subject_id": subject_id,
            "question_count": payload.question_count,
            "header": payload.header.model_dump(),
            "matrix": [],
            "questions": [],
            "status": ExamStatus.DRAFT.value,
            "delivery_mode": "paper",
            "time_limit_seconds": None,
            "scoring_config": None,
            "lms_export_status": "not_exported",
            "blueprint_version": 2,
            "total_marks": 0,
            "selection_seed": None,
            "coverage_report": None,
            "eligibility_manifest": None,
            "revision": 1,
            "created_by_user_id": created_by_user_id,
            "created_at": now,
            "updated_at": now,
        }
        self.repository.create(exam)
        return serialize_exam(exam, 0)

    def get_exam(self, exam_id: str, current_user: CurrentUser) -> dict:
        exam = self._get_for_user_or_404(exam_id, current_user)
        return serialize_exam(exam, self.repository.count_variants(exam_id))

    def duplicate_exam(self, exam_id: str, current_user: CurrentUser) -> dict:
        source = self._get_for_user_or_404(exam_id, current_user)
        snapshot = source.get("finalized_snapshot") or {}
        now = utc_now()
        clone = {
            "_id": ObjectId(),
            "schema_version": SCHEMA_VERSION,
            "name": f"{source['name']} (bản sao)",
            "exam_title": source["exam_title"],
            "subject_id": snapshot.get("subject_id") or source["subject_id"],
            "question_count": snapshot.get("question_count") or source["question_count"],
            "header": deepcopy(snapshot.get("header") or source["header"]),
            "matrix": deepcopy(snapshot.get("matrix") or source.get("matrix", [])),
            "questions": deepcopy(snapshot.get("questions") or source.get("questions", [])),
            "status": ExamStatus.DRAFT.value,
            "delivery_mode": source.get("delivery_mode", "paper"),
            "time_limit_seconds": source.get("time_limit_seconds"),
            "scoring_config": deepcopy(source.get("scoring_config")),
            "lms_export_status": "not_exported",
            "blueprint_version": 2,
            "total_marks": source.get("total_marks", 0),
            "selection_seed": None,
            "coverage_report": None,
            "eligibility_manifest": None,
            "revision": 1,
            "created_by_user_id": current_user.id,
            "created_at": now,
            "updated_at": now,
        }
        self.repository.create(clone)
        return serialize_exam(clone, 0)

    def list_exams(self, page: int, page_size: int, current_user: CurrentUser | None) -> dict:
        owner_user_id = current_user.id if current_user and current_user.role == "Teacher" else None
        exams, total = self.repository.list(page, page_size, owner_user_id)
        items = [serialize_exam(exam, self.repository.count_variants(exam["_id"])) for exam in exams]
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    def question_pool(
        self,
        exam_id: str,
        current_user: CurrentUser,
        *,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        question_type: str | None = None,
        bloom_level: int | None = None,
        chapter_id: str | None = None,
        difficulty: str | None = None,
    ) -> dict:
        exam = self._get_for_user_or_404(exam_id, current_user)
        visible_subjects = (
            active_subject_ids(getattr(self.question_repository, "db", None), current_user.id)
            if current_user.role != "Admin"
            else ()
        )
        pairs, total = self.question_repository.list(
            page,
            page_size,
            APPROVED_STATUS,
            search,
            question_type=question_type,
            bloom_level=bloom_level,
            subject_id=str(exam["subject_id"]),
            chapter_id=chapter_id,
            difficulty=difficulty,
            visible_to_user_id=current_user.id if current_user.role != "Admin" else None,
            visible_subject_ids=visible_subjects,
            approved_current_only=True,
        )
        selected_ids = {str(ref["question_id"]) for ref in exam.get("questions", [])}
        return {
            "items": [
                {
                    **serialize_question(question, version),
                    "in_exam": str(question["_id"]) in selected_ids,
                }
                for question, version in pairs
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def update_status(
        self,
        exam_id: str,
        payload: ExamStatusUpdateRequest,
        current_user: CurrentUser,
    ) -> dict:
        exam = self._get_for_user_or_404(exam_id, current_user)
        current_status = _exam_status(exam)
        target_status = payload.status.value
        if current_status == "ARCHIVED":
            raise ValueError("Đề thi đã lưu trữ")
        if target_status == current_status:
            return serialize_exam(exam, self.repository.count_variants(exam_id))
        if target_status == "DRAFT":
            if current_status == "FINALIZED":
                raise ValueError("Đề thi đã chốt, không thể quay lại nháp")
            updates = {"status": ExamStatus.DRAFT.value}
        elif target_status == "READY":
            if current_status == "FINALIZED":
                raise ValueError("Đề thi đã chốt")
            self._validate_ready_payload(exam)
            updates = {"status": ExamStatus.READY.value}
        elif target_status == "FINALIZED":
            if current_status != "READY":
                raise ValueError("Cần chuyển đề thi sang READY trước khi chốt")
            self._validate_ready_payload(exam)
            updates = {
                "status": ExamStatus.FINALIZED.value,
                "finalized_snapshot": self._finalized_snapshot(exam),
                "finalized_at": utc_now(),
                "revision": int(exam.get("revision", 1)) + 1,
            }
        elif target_status == "ARCHIVED":
            if current_status != "FINALIZED":
                raise ValueError("Chỉ lưu trữ đề thi đã chốt")
            updates = {"status": ExamStatus.ARCHIVED.value}
        else:
            raise ValueError("Trạng thái đề thi không hợp lệ")
        if target_status == "FINALIZED" and hasattr(self.repository, "finalize"):
            updated = self.repository.finalize(exam_id, exam["updated_at"], updates)
            if not updated:
                raise RuntimeError("EXAM_REVISION_CONFLICT")
        else:
            updated = self.repository.update(exam_id, updates)
        return serialize_exam(updated, self.repository.count_variants(exam_id))

    def update_exam(self, exam_id: str, payload: ExamUpdateRequest, current_user: CurrentUser) -> dict:
        current_exam = self._get_for_user_or_404(exam_id, current_user)
        self._assert_mutable(current_exam)
        updates: dict[str, Any] = {}
        if payload.name is not None:
            updates["name"] = payload.name
        if payload.exam_title is not None:
            updates["exam_title"] = payload.exam_title
        if payload.question_count is not None:
            updates["question_count"] = payload.question_count
        if payload.header is not None:
            updates["header"] = payload.header.model_dump()
        if payload.question_count is not None and _exam_status(current_exam) == "READY":
            updates["status"] = ExamStatus.DRAFT.value
        exam = self.repository.update(exam_id, updates) if updates else self._get_or_404(exam_id)
        return serialize_exam(exam, self.repository.count_variants(exam_id))

    def delete_exam(self, exam_id: str, current_user: CurrentUser) -> None:
        exam = self._get_for_user_or_404(exam_id, current_user)
        self._assert_mutable(exam)
        if self.repository.count_variants(exam_id) > 0:
            raise ValueError("Không thể xoá đề thi đã có mã đề, hãy xoá mã đề trước")
        self.repository.delete(exam_id)

    def save_matrix(self, exam_id: str, payload: ExamMatrixRequest, current_user: CurrentUser) -> dict:
        current_exam = self._get_for_user_or_404(exam_id, current_user)
        self._assert_mutable(current_exam)
        cells = [_matrix_cell_dict(cell) for cell in payload.cells]
        total_count = sum(cell["count"] for cell in cells)
        if total_count > int(current_exam["question_count"]):
            raise ValueError("Tổng số câu trong ma trận vượt quá số câu của đề thi")
        updates: dict[str, Any] = {
            "matrix": cells,
            "blueprint_version": 2,
            "total_marks": sum(cell["count"] * cell["marks_per_question"] for cell in cells),
            "coverage_report": None,
        }
        if _exam_status(current_exam) == "READY":
            updates["status"] = ExamStatus.DRAFT.value
        exam = self.repository.update(exam_id, updates)
        return serialize_exam(exam, self.repository.count_variants(exam_id))

    def _find_approved_for_cell(
        self,
        exam: dict,
        cell: dict,
        current_user: CurrentUser | None = None,
    ) -> list[tuple[dict, dict]]:
        return [pair for pair in self._eligible_pairs(exam, current_user) if self._matches_cell(pair[1], cell)]

    def matrix_availability(self, exam_id: str, current_user: CurrentUser) -> list[dict]:
        exam = self._get_for_user_or_404(exam_id, current_user)
        eligible = self._eligible_pairs(exam, current_user)
        results = []
        for cell in exam.get("matrix", []):
            pairs = [pair for pair in eligible if self._matches_cell(pair[1], cell)]
            available = len(pairs)
            results.append(
                {
                    "chapter_id": json_safe(cell.get("chapter_id")),
                    "cognitive_level": cell["cognitive_level"],
                    "bloom_levels": sorted(self._cell_blooms(cell)),
                    "clo_ids": json_safe(cell.get("clo_ids", [])),
                    "question_types": cell.get("question_types", []),
                    "difficulty": cell["difficulty"],
                    "marks_per_question": cell.get("marks_per_question", 1),
                    "requested": cell["count"],
                    "available": available,
                    "sufficient": available >= cell["count"],
                    "shortage": max(0, cell["count"] - available),
                }
            )
        return results

    def auto_generate_pool(self, exam_id: str, current_user: CurrentUser) -> dict:
        exam = self._get_for_user_or_404(exam_id, current_user)
        self._assert_mutable(exam)
        matrix = exam.get("matrix", [])
        if not matrix:
            raise ValueError("Chưa cấu hình ma trận đề thi")
        seed = hashlib.sha256(f"{exam_id}:{exam.get('revision', 1)}".encode()).hexdigest()[:24]
        eligible = self._eligible_pairs(exam, current_user)
        chosen, report = self._allocate(exam, eligible, seed)
        if not report["valid"]:
            raise ValueError("Không thể cấp phát blueprint: " + json.dumps(json_safe(report), ensure_ascii=False))
        selected_refs = [
            {
                "question_id": question["_id"],
                "version_id": version["_id"],
                "content_snapshot": serialize_question(question, version),
            }
            for question, version in chosen
        ]
        updates: dict[str, Any] = {
            "questions": selected_refs,
            "selection_seed": seed,
            "coverage_report": report,
            "eligibility_manifest": {
                "policy": "approved-current-visible-subject-v1",
                "eligible_count": len(eligible),
                "evaluated_at": utc_now(),
            },
        }
        if _exam_status(exam) == "READY":
            updates["status"] = ExamStatus.DRAFT.value
        updated = self.repository.update(exam_id, updates)
        return serialize_exam(updated, self.repository.count_variants(exam_id))

    def add_questions_manual(self, exam_id: str, payload: AddQuestionsManualRequest, current_user: CurrentUser) -> dict:
        exam = self._get_for_user_or_404(exam_id, current_user)
        self._assert_mutable(exam)
        eligible_by_id = {
            str(question["_id"]): (question, version) for question, version in self._eligible_pairs(exam, current_user)
        }
        existing_refs = list(exam.get("questions", []))
        existing_ids = {str(ref["question_id"]) for ref in existing_refs}
        new_refs = []
        for question_id in payload.question_ids:
            if question_id in existing_ids:
                continue
            pair = eligible_by_id.get(question_id)
            if not pair:
                raise ValueError(f"Câu hỏi không thuộc eligible pool của đề: {question_id}")
            question, version = pair
            self._assert_question_can_join_exam(exam, question, version)
            existing_ids.add(question_id)
            new_refs.append(
                {
                    "question_id": question["_id"],
                    "version_id": version["_id"],
                    "content_snapshot": serialize_question(question, version),
                }
            )
        total = existing_refs + new_refs
        if len(total) > exam["question_count"]:
            raise ValueError(f"Tổng số câu hỏi ({len(total)}) vượt quá số câu đã khai báo ({exam['question_count']})")
        updates: dict[str, Any] = {"questions": total}
        if _exam_status(exam) == "READY":
            updates["status"] = ExamStatus.DRAFT.value
        updated = self.repository.update(exam_id, updates)
        return serialize_exam(updated, self.repository.count_variants(exam_id))

    def remove_question(self, exam_id: str, question_id: str, current_user: CurrentUser) -> dict:
        exam = self._get_for_user_or_404(exam_id, current_user)
        self._assert_mutable(exam)
        remaining = [ref for ref in exam.get("questions", []) if str(ref["question_id"]) != question_id]
        updates: dict[str, Any] = {"questions": remaining}
        if _exam_status(exam) == "READY":
            updates["status"] = ExamStatus.DRAFT.value
        updated = self.repository.update(exam_id, updates)
        return serialize_exam(updated, self.repository.count_variants(exam_id))


class ExamVariantService:
    def __init__(self, exams: ExamRepository, variants: ExamVariantRepository):
        self.exams = exams
        self.variants = variants

    def _get_exam_or_404(self, exam_id: str) -> dict:
        exam = self.exams.find(exam_id)
        if not exam:
            raise LookupError("Không tìm thấy đề thi")
        return exam

    def _get_exam_for_user_or_404(self, exam_id: str, current_user: CurrentUser | None) -> dict:
        exam = self._get_exam_or_404(exam_id)
        ExamService._assert_can_access(exam, current_user, self.exams)
        return exam

    def get_exam_variant_pair(
        self,
        exam_id: str,
        variant_id: str,
        current_user: CurrentUser | None,
    ) -> tuple[dict, dict]:
        exam = self._get_exam_for_user_or_404(exam_id, current_user)
        variant = self.variants.find(variant_id)
        if not variant or str(variant["exam_id"]) != exam_id:
            raise LookupError("Không tìm thấy mã đề")
        return exam, variant

    def create_variant(self, exam_id: str, payload: ExamVariantCreateRequest, current_user: CurrentUser) -> dict:
        exam = self._get_exam_for_user_or_404(exam_id, current_user)
        if _exam_status(exam) != "FINALIZED":
            raise ValueError("Chỉ có thể tạo mã đề sau khi chốt đề thi")
        questions = (exam.get("finalized_snapshot") or {}).get("questions") or exam.get("questions", [])
        if not questions:
            raise ValueError("Đề thi chưa có câu hỏi, không thể tạo mã đề")
        if len(questions) != int(exam["question_count"]):
            raise ValueError("Đề thi chưa đủ số câu, không thể tạo mã đề")
        if self.exams.count_variants(exam_id) >= MAX_VARIANTS_PER_EXAM:
            raise ValueError(f"Đã đạt tối đa {MAX_VARIANTS_PER_EXAM} mã đề cho kỳ thi này")

        snapshot_digest = hashlib.sha256(
            json.dumps(json_safe(questions), ensure_ascii=False, sort_keys=True, default=str).encode()
        ).hexdigest()
        seed = hashlib.sha256(f"{exam_id}:{payload.exam_code}:{snapshot_digest}".encode()).hexdigest()[:24]
        rng = random.Random(seed)
        ordered = list(questions)
        if payload.shuffle:
            ordered = ordered[:]
            rng.shuffle(ordered)

        variant_questions = []
        answer_key: dict[str, Any] = {}
        for index, ref in enumerate(ordered, start=1):
            snapshot = ref["content_snapshot"]
            question_data = snapshot.get("question_data") or {}
            options = question_data.get("options")
            option_order = None
            answer_mapping: dict[str, str] = {}
            correct_answer = question_data.get("correct_answer")
            qtype = str((snapshot.get("classification") or {}).get("assessment_type") or "").lower()
            shuffleable = qtype in {"trac_nghiem", "tinh_huong", "nhieu_lua_chon", "sap_xep"}
            unsafe = any(
                marker in str(value).casefold()
                for value in (options or {}).values()
                for marker in ("cả a và b", "tất cả phương án trên", "tất cả đáp án trên")
            )
            if payload.shuffle and qtype == "ghep_cot" and isinstance(options, dict):
                alpha = [key for key in options if key.isalpha()]
                display_alpha = alpha[:]
                rng.shuffle(display_alpha)
                answer_mapping = dict(zip(alpha, display_alpha))
                remapped = {
                    **{key: value for key, value in options.items() if not key.isalpha()},
                    **{answer_mapping[key]: options[key] for key in alpha},
                }
                question_data = {
                    **question_data,
                    "options": dict(sorted(remapped.items(), key=lambda item: (item[0].isalpha(), item[0]))),
                    "correct_answer": re.sub(
                        r"(?<=-)([A-Za-z])",
                        lambda match: answer_mapping.get(match.group(1).upper(), match.group(1).upper()),
                        str(correct_answer or ""),
                    ),
                }
                snapshot = {**snapshot, "question_data": question_data}
                correct_answer = question_data["correct_answer"]
            elif payload.shuffle and shuffleable and isinstance(options, dict) and not unsafe:
                keys = list(options)
                display_keys = keys[:]
                rng.shuffle(display_keys)
                answer_mapping = dict(zip(keys, display_keys))
                inverse_mapping = {display: original for original, display in answer_mapping.items()}
                shuffled_options = {display: options[inverse_mapping[display]] for display in sorted(display_keys)}
                option_order = [keys.index(inverse_mapping[display]) for display in sorted(display_keys)]
                if isinstance(correct_answer, str):
                    correct_keys = [
                        part.strip() for part in correct_answer.replace(";", ",").split(",") if part.strip()
                    ]
                    correct_answer = ",".join(answer_mapping.get(key, key) for key in correct_keys)
                question_data = {**question_data, "options": shuffled_options, "correct_answer": correct_answer}
                snapshot = {**snapshot, "question_data": question_data}
            variant_questions.append(
                {
                    "order": index,
                    "question_id": ref["question_id"],
                    "content_snapshot": snapshot,
                    "option_order": option_order,
                    "answer_mapping": answer_mapping,
                }
            )
            answer_key[str(ref["question_id"])] = correct_answer

        variant = {
            "_id": ObjectId(),
            "schema_version": SCHEMA_VERSION,
            "exam_id": object_id(exam_id, "exam_id"),
            "exam_code": payload.exam_code,
            "questions": variant_questions,
            "answer_key": answer_key,
            "seed": seed,
            "exam_revision": int((exam.get("finalized_snapshot") or {}).get("revision") or exam.get("revision", 1)),
            "permutation": [str(ref["question_id"]) for ref in ordered],
            "snapshot_sha256": snapshot_digest,
            "export_manifest": {
                "manifest_version": 1,
                "exam_id": exam_id,
                "exam_revision": int((exam.get("finalized_snapshot") or {}).get("revision") or exam.get("revision", 1)),
                "variant_code": payload.exam_code,
                "snapshot_sha256": snapshot_digest,
            },
            "created_at": utc_now(),
        }
        self.variants.create(variant)
        return serialize_variant(variant)

    def list_variants(self, exam_id: str, current_user: CurrentUser) -> list[dict]:
        self._get_exam_for_user_or_404(exam_id, current_user)
        return [serialize_variant(v) for v in self.variants.list_by_exam(exam_id)]

    def get_variant(self, exam_id: str, variant_id: str, current_user: CurrentUser) -> dict:
        _exam, variant = self.get_exam_variant_pair(exam_id, variant_id, current_user)
        return serialize_variant(variant)

    def delete_variant(self, exam_id: str, variant_id: str, current_user: CurrentUser) -> None:
        _exam, variant = self.get_exam_variant_pair(exam_id, variant_id, current_user)
        self.variants.delete(variant_id)

    def build_preview(self, exam_id: str, variant_id: str, current_user: CurrentUser) -> dict:
        exam, variant = self.get_exam_variant_pair(exam_id, variant_id, current_user)
        questions = []
        for entry in sorted(variant["questions"], key=lambda item: item["order"]):
            snapshot = entry["content_snapshot"]
            question_data = snapshot.get("question_data") or {}
            options = question_data.get("options") or {}
            questions.append(
                {
                    "number": entry["order"],
                    "content": snapshot.get("content", ""),
                    "question_type": (snapshot.get("classification") or {}).get("assessment_type", ""),
                    "options": [{"label": key, "text": value} for key, value in options.items()],
                }
            )
        return json_safe(
            {
                "header": exam["header"],
                "exam_code": variant["exam_code"],
                "questions": questions,
                "answers": [
                    {"number": entry["order"], "answer": variant["answer_key"].get(str(entry["question_id"]), "")}
                    for entry in sorted(variant["questions"], key=lambda item: item["order"])
                ],
                "export_manifest": variant.get("export_manifest", {}),
            }
        )


def get_exam_service() -> ExamService:
    database = get_database()
    return ExamService(MongoExamRepository(database), MongoQuestionRepository(database))


def get_exam_variant_service() -> ExamVariantService:
    database = get_database()
    return ExamVariantService(MongoExamRepository(database), MongoExamVariantRepository(database))
