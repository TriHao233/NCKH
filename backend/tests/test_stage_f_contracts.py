from datetime import datetime, timezone

from bson import ObjectId

from core.dependencies import CurrentUser
from modules.exams.pdf_service import render_exam_html
from modules.exams.schemas import ExamVariantCreateRequest, MatrixCell
from modules.exams.service import ExamService, ExamVariantService


def _user():
    oid = ObjectId()
    return CurrentUser(
        id=oid,
        firebase_uid=str(oid),
        email="teacher@example.com",
        role="Teacher",
        is_active=True,
        permissions=(),
        display_name="Teacher",
    )


def _pair(subject_id, bloom, clos=()):
    question_id, version_id = ObjectId(), ObjectId()
    question = {
        "_id": question_id,
        "question_code": str(question_id),
        "review_status": "APPROVED",
        "current_version_id": version_id,
        "approved_version_id": version_id,
    }
    version = {
        "_id": version_id,
        "classification": {
            "subject": {"id": subject_id},
            "bloom": {"level": bloom},
            "difficulty": "de",
            "assessment_type": "TRAC_NGHIEM",
        },
        "clos": [{"id": value} for value in clos],
    }
    return question, version


def test_legacy_high_cognitive_level_preserves_bloom_five_and_six():
    cell = MatrixCell(cognitive_level="van_dung_cao", difficulty="kho", count=2)
    assert cell.bloom_levels == [4, 5, 6]


def test_overlap_allocator_uses_scarce_cell_first():
    subject_id, clo_id = ObjectId(), ObjectId()
    broad = _pair(subject_id, 1)
    scarce = _pair(subject_id, 1, (clo_id,))
    exam = {
        "matrix": [
            {"bloom_levels": [1], "difficulty": "de", "count": 1},
            {"bloom_levels": [1], "clo_ids": [clo_id], "difficulty": "de", "count": 1},
        ]
    }
    selected, report = ExamService(None, None)._allocate(exam, [scarce, broad], "fixed")
    assignment = {row["cell_index"]: row["question_id"] for row in report["assignments"]}
    assert report["valid"] is True
    assert len(selected) == 2
    assert assignment[1] == str(scarce[0]["_id"])
    assert assignment[0] == str(broad[0]["_id"])


class _Exams:
    def __init__(self, exam):
        self.exam = exam

    def find(self, _exam_id):
        return self.exam

    def count_variants(self, _exam_id):
        return 0


class _Variants:
    def __init__(self):
        self.value = None

    def create(self, value):
        self.value = value
        return value


def test_typed_shuffler_keeps_stable_answer_mapping_and_seed():
    user = _user()
    rows = []
    definitions = [
        ("NHIEU_LUA_CHON", {"A": "a", "B": "b", "C": "c", "D": "d"}, "A,C"),
        ("GHEP_COT", {"1": "one", "2": "two", "3": "three", "A": "a", "B": "b", "C": "c", "D": "x"}, "1-A,2-B,3-C"),
        ("SAP_XEP", {"A": "one", "B": "two", "C": "three", "D": "four"}, "A,B,C,D"),
        ("DUNG_SAI", {"A": "Đúng", "B": "Sai"}, "A"),
    ]
    for qtype, options, answer in definitions:
        question_id = ObjectId()
        rows.append(
            {
                "question_id": question_id,
                "version_id": ObjectId(),
                "content_snapshot": {
                    "content": qtype,
                    "classification": {"assessment_type": qtype},
                    "question_data": {"options": options, "correct_answer": answer},
                },
            }
        )
    exam = {
        "_id": ObjectId(),
        "created_by_user_id": user.id,
        "subject_id": ObjectId(),
        "status": "FINALIZED",
        "question_count": len(rows),
        "questions": rows,
        "finalized_snapshot": {"questions": rows, "revision": 2},
    }
    first = ExamVariantService(_Exams(exam), _Variants()).create_variant(
        str(exam["_id"]), ExamVariantCreateRequest(exam_code="101"), user
    )
    second = ExamVariantService(_Exams(exam), _Variants()).create_variant(
        str(exam["_id"]), ExamVariantCreateRequest(exam_code="101"), user
    )
    assert first["seed"] == second["seed"]
    assert first["permutation"] == second["permutation"]
    for entry in first["questions"]:
        qtype = entry["content_snapshot"]["classification"]["assessment_type"]
        if qtype == "DUNG_SAI":
            assert entry["answer_mapping"] == {}
            assert first["answer_key"][entry["question_id"]] == "A"
        else:
            assert entry["answer_mapping"]


def test_student_export_contains_no_answer_or_explanation():
    html = render_exam_html(
        {"exam_name": "Midterm", "duration_minutes": 60},
        "101",
        [
            {
                "order": 1,
                "content_snapshot": {
                    "content": "Question",
                    "question_data": {
                        "options": {"A": "public option", "B": "other option"},
                        "correct_answer": "A",
                        "explanation": "SECRET EXPLANATION",
                    },
                },
            }
        ],
        "de",
    )
    assert "SECRET EXPLANATION" not in html
    assert 'class="answer-table"' not in html
    assert "public option" in html
