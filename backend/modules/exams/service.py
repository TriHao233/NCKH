from __future__ import annotations

import random
from typing import Any

from bson import ObjectId

from core.bootstrap import SCHEMA_VERSION
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
    ExamUpdateRequest,
    ExamVariantCreateRequest,
    MatrixCell,
)
from modules.questions.repository import MongoQuestionRepository, serialize_question

APPROVED_STATUS = "APPROVED"


def _matrix_cell_dict(cell: MatrixCell) -> dict:
    return {
        "chapter_id": object_id(cell.chapter_id, "chapter_id") if cell.chapter_id else None,
        "cognitive_level": cell.cognitive_level.value,
        "difficulty": cell.difficulty.value,
        "count": cell.count,
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
            "status": exam["status"],
            "variant_count": variant_count,
            "delivery_mode": exam.get("delivery_mode", "paper"),
            "time_limit_seconds": exam.get("time_limit_seconds"),
            "scoring_config": exam.get("scoring_config"),
            "lms_export_status": exam.get("lms_export_status", "not_exported"),
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

    def create_exam(self, payload: ExamCreateRequest, created_by_user_id: ObjectId) -> dict:
        now = utc_now()
        exam = {
            "_id": ObjectId(),
            "schema_version": SCHEMA_VERSION,
            "name": payload.name,
            "exam_title": payload.exam_title,
            "subject_id": object_id(payload.subject_id, "subject_id"),
            "question_count": payload.question_count,
            "header": payload.header.model_dump(),
            "matrix": [],
            "questions": [],
            "status": "draft",
            "delivery_mode": "paper",
            "time_limit_seconds": None,
            "scoring_config": None,
            "lms_export_status": "not_exported",
            "created_by_user_id": created_by_user_id,
            "created_at": now,
            "updated_at": now,
        }
        self.repository.create(exam)
        return serialize_exam(exam, 0)

    def get_exam(self, exam_id: str) -> dict:
        exam = self._get_or_404(exam_id)
        return serialize_exam(exam, self.repository.count_variants(exam_id))

    def list_exams(self, page: int, page_size: int, current_user: CurrentUser | None) -> dict:
        owner_user_id = (
            current_user.id
            if current_user and current_user.role == "Teacher"
            else None
        )
        exams, total = self.repository.list(page, page_size, owner_user_id)
        items = [
            serialize_exam(exam, self.repository.count_variants(exam["_id"]))
            for exam in exams
        ]
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    def update_exam(self, exam_id: str, payload: ExamUpdateRequest) -> dict:
        self._get_or_404(exam_id)
        updates: dict[str, Any] = {}
        if payload.name is not None:
            updates["name"] = payload.name
        if payload.exam_title is not None:
            updates["exam_title"] = payload.exam_title
        if payload.question_count is not None:
            updates["question_count"] = payload.question_count
        if payload.header is not None:
            updates["header"] = payload.header.model_dump()
        exam = self.repository.update(exam_id, updates) if updates else self._get_or_404(exam_id)
        return serialize_exam(exam, self.repository.count_variants(exam_id))

    def delete_exam(self, exam_id: str) -> None:
        self._get_or_404(exam_id)
        if self.repository.count_variants(exam_id) > 0:
            raise ValueError("Không thể xoá đề thi đã có mã đề, hãy xoá mã đề trước")
        self.repository.delete(exam_id)

    def save_matrix(self, exam_id: str, payload: ExamMatrixRequest) -> dict:
        self._get_or_404(exam_id)
        cells = [_matrix_cell_dict(cell) for cell in payload.cells]
        exam = self.repository.update(exam_id, {"matrix": cells})
        return serialize_exam(exam, self.repository.count_variants(exam_id))

    def _find_approved_for_cell(self, exam: dict, cell: dict) -> list[tuple[dict, dict]]:
        bloom_level = COGNITIVE_LEVEL_TO_BLOOM.get(cell["cognitive_level"])
        chapter_id = str(cell["chapter_id"]) if cell.get("chapter_id") else None
        pairs, _total = self.question_repository.list(
            1,
            1000,
            APPROVED_STATUS,
            None,
            bloom_level=bloom_level,
            subject_id=str(exam["subject_id"]),
            chapter_id=chapter_id,
            difficulty=cell["difficulty"],
        )
        return pairs

    def matrix_availability(self, exam_id: str) -> list[dict]:
        exam = self._get_or_404(exam_id)
        results = []
        for cell in exam.get("matrix", []):
            pairs = self._find_approved_for_cell(exam, cell)
            available = len(pairs)
            results.append(
                {
                    "chapter_id": json_safe(cell.get("chapter_id")),
                    "cognitive_level": cell["cognitive_level"],
                    "difficulty": cell["difficulty"],
                    "requested": cell["count"],
                    "available": available,
                    "sufficient": available >= cell["count"],
                }
            )
        return results

    def auto_generate_pool(self, exam_id: str) -> dict:
        exam = self._get_or_404(exam_id)
        matrix = exam.get("matrix", [])
        if not matrix:
            raise ValueError("Chưa cấu hình ma trận đề thi")
        selected_ids: set[str] = set()
        selected_refs: list[dict] = []
        shortages: list[dict] = []
        for cell in matrix:
            pairs = self._find_approved_for_cell(exam, cell)
            pool = [pair for pair in pairs if str(pair[0]["_id"]) not in selected_ids]
            if len(pool) < cell["count"]:
                shortages.append(
                    {
                        "chapter_id": json_safe(cell.get("chapter_id")),
                        "cognitive_level": cell["cognitive_level"],
                        "difficulty": cell["difficulty"],
                        "requested": cell["count"],
                        "available": len(pool),
                    }
                )
                continue
            chosen = random.sample(pool, cell["count"])
            for question, version in chosen:
                selected_ids.add(str(question["_id"]))
                selected_refs.append(
                    {
                        "question_id": question["_id"],
                        "version_id": version["_id"],
                        "content_snapshot": serialize_question(question, version),
                    }
                )
        if shortages:
            raise ValueError(
                "Không đủ câu hỏi đã duyệt cho một số nhóm trong ma trận: "
                + str(shortages)
            )
        if len(selected_refs) > exam["question_count"]:
            selected_refs = selected_refs[: exam["question_count"]]
        updated = self.repository.update(exam_id, {"questions": selected_refs})
        return serialize_exam(updated, self.repository.count_variants(exam_id))

    def add_questions_manual(self, exam_id: str, payload: AddQuestionsManualRequest) -> dict:
        exam = self._get_or_404(exam_id)
        existing_refs = list(exam.get("questions", []))
        existing_ids = {str(ref["question_id"]) for ref in existing_refs}
        new_refs = []
        for question_id in payload.question_ids:
            if question_id in existing_ids:
                continue
            pair = self.question_repository.find_pair(question_id)
            if not pair:
                raise ValueError(f"Câu hỏi không tồn tại: {question_id}")
            question, version = pair
            if question.get("review_status") != APPROVED_STATUS:
                raise ValueError(
                    f"Câu hỏi {question.get('question_code')} chưa được duyệt"
                )
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
            raise ValueError(
                f"Tổng số câu hỏi ({len(total)}) vượt quá số câu đã khai báo ({exam['question_count']})"
            )
        updated = self.repository.update(exam_id, {"questions": total})
        return serialize_exam(updated, self.repository.count_variants(exam_id))

    def remove_question(self, exam_id: str, question_id: str) -> dict:
        exam = self._get_or_404(exam_id)
        remaining = [
            ref
            for ref in exam.get("questions", [])
            if str(ref["question_id"]) != question_id
        ]
        updated = self.repository.update(exam_id, {"questions": remaining})
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

    def create_variant(self, exam_id: str, payload: ExamVariantCreateRequest) -> dict:
        exam = self._get_exam_or_404(exam_id)
        questions = exam.get("questions", [])
        if not questions:
            raise ValueError("Đề thi chưa có câu hỏi, không thể tạo mã đề")
        if self.exams.count_variants(exam_id) >= MAX_VARIANTS_PER_EXAM:
            raise ValueError(f"Đã đạt tối đa {MAX_VARIANTS_PER_EXAM} mã đề cho kỳ thi này")

        ordered = list(questions)
        if payload.shuffle:
            ordered = ordered[:]
            random.shuffle(ordered)

        variant_questions = []
        answer_key: dict[str, Any] = {}
        for index, ref in enumerate(ordered, start=1):
            snapshot = ref["content_snapshot"]
            question_data = snapshot.get("question_data") or {}
            options = question_data.get("options")
            option_order = None
            correct_answer = question_data.get("correct_answer")
            if payload.shuffle and isinstance(options, dict) and set(options.keys()) <= {"A", "B", "C", "D", "E"}:
                keys = list(options.keys())
                shuffled_keys = keys[:]
                random.shuffle(shuffled_keys)
                key_map = dict(zip(keys, shuffled_keys))
                shuffled_options = {key_map[k]: v for k, v in options.items()}
                option_order = [ord(key_map[k]) - ord("A") for k in keys]
                if isinstance(correct_answer, str):
                    correct_keys = [c.strip() for c in correct_answer.split(",") if c.strip()]
                    correct_answer = ",".join(key_map.get(k, k) for k in correct_keys)
                question_data = {**question_data, "options": shuffled_options, "correct_answer": correct_answer}
                snapshot = {**snapshot, "question_data": question_data}
            variant_questions.append(
                {
                    "order": index,
                    "question_id": ref["question_id"],
                    "content_snapshot": snapshot,
                    "option_order": option_order,
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
            "created_at": utc_now(),
        }
        self.variants.create(variant)
        return serialize_variant(variant)

    def list_variants(self, exam_id: str) -> list[dict]:
        self._get_exam_or_404(exam_id)
        return [serialize_variant(v) for v in self.variants.list_by_exam(exam_id)]

    def get_variant(self, exam_id: str, variant_id: str) -> dict:
        self._get_exam_or_404(exam_id)
        variant = self.variants.find(variant_id)
        if not variant or str(variant["exam_id"]) != exam_id:
            raise LookupError("Không tìm thấy mã đề")
        return serialize_variant(variant)

    def delete_variant(self, exam_id: str, variant_id: str) -> None:
        self._get_exam_or_404(exam_id)
        variant = self.variants.find(variant_id)
        if not variant or str(variant["exam_id"]) != exam_id:
            raise LookupError("Không tìm thấy mã đề")
        self.variants.delete(variant_id)

    def build_preview(self, exam_id: str, variant_id: str) -> dict:
        exam = self._get_exam_or_404(exam_id)
        variant = self.variants.find(variant_id)
        if not variant or str(variant["exam_id"]) != exam_id:
            raise LookupError("Không tìm thấy mã đề")
        questions = []
        for entry in sorted(variant["questions"], key=lambda item: item["order"]):
            snapshot = entry["content_snapshot"]
            question_data = snapshot.get("question_data") or {}
            options = question_data.get("options") or {}
            questions.append(
                {
                    "number": entry["order"],
                    "content": snapshot.get("content", ""),
                    "question_type": (snapshot.get("classification") or {}).get(
                        "assessment_type", ""
                    ),
                    "options": [
                        {"label": key, "text": value} for key, value in options.items()
                    ],
                }
            )
        return json_safe(
            {
                "header": exam["header"],
                "exam_code": variant["exam_code"],
                "questions": questions,
            }
        )


def get_exam_service() -> ExamService:
    database = get_database()
    return ExamService(MongoExamRepository(database), MongoQuestionRepository(database))


def get_exam_variant_service() -> ExamVariantService:
    database = get_database()
    return ExamVariantService(
        MongoExamRepository(database), MongoExamVariantRepository(database)
    )
