from copy import deepcopy
from io import BytesIO
import asyncio
from unittest.mock import Mock

import pytest
from bson import ObjectId
from docx import Document
from pypdf import PdfReader
from pydantic import ValidationError

from modules.exams.pdf_service import _build_context, _pdf_font_faces, render_exam_docx, render_exam_html, render_exam_pdf
from modules.exams.schemas import (
    COGNITIVE_LEVEL_TO_BLOOM,
    CognitiveLevel,
    ExamCreateRequest,
    ExamMatrixRequest,
    ExamUpdateRequest,
    ExamVariantCreateRequest,
    MatrixCell,
)
from modules.exams.service import ExamService, ExamVariantService, serialize_exam
from test_schema_v2 import FakeExamRepository, FakeExamVariantRepository, _current_user, _exam_doc


def question_pair(exam, *, answer="A", assessment_type="TRAC_NGHIEM"):
    question_id, version_id = ObjectId(), ObjectId()
    return (
        {
            "_id": question_id, "question_code": f"Q-{question_id}", "current_version": 1,
            "current_version_id": version_id, "approved_version_id": version_id,
            "lifecycle_status": "ACTIVE", "evaluation_status": "PASSED",
            "review_status": "APPROVED", "publication_status": "NOT_PUBLISHED",
            "created_at": exam["created_at"], "updated_at": exam["updated_at"],
        },
        {
            "_id": version_id, "content": "Nội dung câu hỏi", "content_hash": "test-hash",
            "question_data": {"options": {"A": "Alpha", "B": "Beta", "C": "Gamma"}, "correct_answer": answer},
            "classification": {"subject": {"id": exam["subject_id"]}, "assessment_type": assessment_type},
        },
    )


def matrix_service(pools, counts=None):
    owner = _current_user("Teacher")
    exam = _exam_doc(owner.id)
    counts = counts or [1] * len(pools)
    exam["question_count"] = sum(counts)
    exam["matrix"] = [
        {"chapter_id": None, "cognitive_level": "nho", "count": count, "group": index}
        for index, count in enumerate(counts)
    ]
    service = ExamService(FakeExamRepository([exam]), Mock())
    service._find_approved_for_cell = lambda _exam, cell, _user: pools[cell["group"]]
    return service, exam, owner


@pytest.mark.parametrize("value,level", [*COGNITIVE_LEVEL_TO_BLOOM.items(),
    ("nhan_biet", 1), ("thong_hieu", 2), ("van_dung_cao", 4)])
def test_matrix_supports_six_bloom_levels_and_legacy_values(value, level):
    cell = MatrixCell(cognitive_level=value, count=1)
    assert COGNITIVE_LEVEL_TO_BLOOM[cell.cognitive_level.value] == level
    assert len(CognitiveLevel) == 6


def test_reading_legacy_exam_normalizes_without_mutating_stored_matrix():
    exam = _exam_doc(ObjectId())
    exam["matrix"] = [{"cognitive_level": "van_dung_cao", "count": 1}]
    assert serialize_exam(exam)["matrix"][0]["cognitive_level"] == "phan_tich"
    assert exam["matrix"][0]["cognitive_level"] == "van_dung_cao"


@pytest.mark.parametrize("value", ["nho", "hieu", "van_dung", "phan_tich", "danh_gia", "sang_tao"])
def test_matrix_query_uses_exact_bloom_level(value):
    owner = _current_user("Teacher")
    exam = _exam_doc(owner.id)
    questions = Mock()
    questions.list.return_value = ([], 0)
    service = ExamService(FakeExamRepository([exam]), questions)
    service.save_matrix(str(exam["_id"]), ExamMatrixRequest(cells=[{"cognitive_level": value, "count": 1}]), owner)
    service.matrix_availability(str(exam["_id"]), owner)
    assert questions.list.call_args.kwargs["bloom_level"] == COGNITIVE_LEVEL_TO_BLOOM[value]


def test_overlapping_groups_reassign_questions_and_never_duplicate_them():
    pairs = [question_pair(_exam_doc(ObjectId())) for _ in range(3)]
    service, exam, owner = matrix_service([[pairs[0], pairs[1]], [pairs[1], pairs[2]], [pairs[0], pairs[1]]])
    assert all(row["sufficient"] for row in service.matrix_availability(str(exam["_id"]), owner))
    # This graph needs an augmenting path with the original candidate order.
    _, allocated = service._allocate_matrix(exam, owner)
    assert [len(group) for group in allocated] == [1, 1, 1]
    result = service.auto_generate_pool(str(exam["_id"]), owner)
    assert len({ref["question_id"] for ref in result["questions"]}) == 3


def test_shared_shortage_is_reported_and_existing_questions_are_preserved():
    pair = question_pair(_exam_doc(ObjectId()))
    service, exam, owner = matrix_service([[pair], [pair]])
    exam["questions"] = [{"question_id": "keep-existing-question"}]
    rows = service.matrix_availability(str(exam["_id"]), owner)
    assert not all(row["sufficient"] for row in rows)
    with pytest.raises(ValueError, match="Không đủ"):
        service.auto_generate_pool(str(exam["_id"]), owner)
    assert exam["questions"] == [{"question_id": "keep-existing-question"}]


def test_auto_selection_requires_matrix_total_to_equal_exam_count():
    service, exam, owner = matrix_service([[]])
    exam["question_count"] = 2
    with pytest.raises(ValueError, match="khớp"):
        service.auto_generate_pool(str(exam["_id"]), owner)


def test_matrix_query_reads_beyond_first_thousand_candidates():
    owner = _current_user("Teacher")
    exam = _exam_doc(owner.id)
    usable = question_pair(exam)
    stale = deepcopy(usable)
    stale[0]["approved_version_id"] = ObjectId()
    questions = Mock()
    questions.list.side_effect = [([stale] * 1000, 1001), ([usable], 1001)]
    service = ExamService(FakeExamRepository([exam]), questions)
    assert service._find_approved_for_cell(exam, {"cognitive_level": "nhan_biet"}, owner) == [usable]
    assert [call.args[0] for call in questions.list.call_args_list] == [1, 2]


@pytest.mark.parametrize("existing", ["questions", "matrix"])
def test_reducing_question_target_does_not_invalidate_existing_content(existing):
    owner = _current_user("Teacher")
    exam = _exam_doc(owner.id)
    exam["question_count"] = 2
    exam[existing] = [{"count": 2}] if existing == "matrix" else [{}, {}]
    service = ExamService(FakeExamRepository([exam]), Mock())
    with pytest.raises(ValueError, match="ít hơn"):
        service.update_exam(str(exam["_id"]), ExamUpdateRequest(question_count=1), owner)
    assert exam["question_count"] == 2


@pytest.mark.parametrize("payload", [
    lambda: ExamCreateRequest(name=" ", exam_title="Title", subject_id="subject", question_count=1),
    lambda: ExamUpdateRequest(exam_title=" "),
    lambda: ExamVariantCreateRequest(exam_code=" "),
    lambda: ExamVariantCreateRequest(exam_code='code"'),
])
def test_invalid_titles_and_codes_are_rejected(payload):
    with pytest.raises(ValidationError):
        payload()


def test_shuffling_remaps_list_answers_and_preserves_source_snapshot(monkeypatch):
    owner = _current_user("Teacher")
    exam = _exam_doc(owner.id)
    pair = question_pair(exam, answer=["A", "C"], assessment_type="NHIEU_LUA_CHON")
    from modules.questions.repository import serialize_question
    snapshot = serialize_question(*pair)
    original = deepcopy(snapshot)
    exam.update(status="FINALIZED", questions=[{"question_id": pair[0]["_id"], "content_snapshot": snapshot}])
    monkeypatch.setattr("modules.exams.service.random.shuffle", lambda items: items.reverse())
    service = ExamVariantService(FakeExamRepository([exam]), FakeExamVariantRepository())
    result = service.create_variant(str(exam["_id"]), ExamVariantCreateRequest(exam_code=" 101 "), owner)
    data = result["questions"][0]["content_snapshot"]["question_data"]
    assert data["correct_answer"] == ["C", "A"]
    assert [data["options"][key] for key in data["correct_answer"]] == ["Alpha", "Gamma"]
    assert snapshot == original
    assert result["exam_code"] == "101"
    preview = service.build_preview(str(exam["_id"]), result["id"], owner)
    assert [option["label"] for option in preview["questions"][0]["options"]] == ["A", "B", "C"]


def test_exports_preserve_ordered_answer_and_sort_option_labels():
    questions = [{"order": 1, "content_snapshot": {
        "content": "Sắp xếp các bước", "classification": {"assessment_type": "SAP_XEP"},
        "question_data": {"options": {"C": "Cuối", "A": "Đầu", "B": "Giữa"}, "correct_answer": "C,A,B"},
    }}]
    context = _build_context({}, "101", questions, "de_dapan")
    assert context["answer_rows"][0]["answer"] == "C, A, B"
    assert [option["label"] for option in context["questions"][0]["options"]] == ["A", "B", "C"]
    assert "C, A, B" in render_exam_html({}, "101", questions, "dapan")
    doc = Document(BytesIO(render_exam_docx({}, "101", questions, "de_dapan")))
    assert doc.tables[0].rows[1].cells[1].text == "C, A, B"
    for style_name in ("Normal", "Heading 1", "Heading 2", "Table Grid"):
        style = doc.styles[style_name]
        assert style.font.name == "Times New Roman"
        assert style.font.size.pt == 13
        assert style.paragraph_format.line_spacing == 1.3
    html = render_exam_html({}, "101", questions, "de_dapan")
    assert "font-size: 13pt; line-height: 1.3" in html


def test_pdf_rendering_produces_real_pdf_with_ordered_answers():
    questions = [{"order": 1, "content_snapshot": {
        "content": "Sắp xếp các bước", "question_data": {"options": {"A": "Đầu", "B": "Cuối"}, "correct_answer": "B,A"},
    }}]
    result = asyncio.run(render_exam_pdf({"subject_name": "Kiểm thử"}, "101", questions, "de_dapan"))
    assert result.startswith(b"%PDF-")
    assert len(result) > 1000
    if _pdf_font_faces():
        pdf = PdfReader(BytesIO(result))
        font_names = {
            str(font.get_object().get("/BaseFont"))
            for page in pdf.pages
            for font in page["/Resources"]["/Font"].get_object().values()
        }
        assert any("TimesNewRoman" in name for name in font_names)


def test_docx_download_supports_unicode_exam_codes():
    from fastapi.testclient import TestClient
    from main import app
    from core.dependencies import require_exam_manager
    from modules.exams.service import get_exam_variant_service

    owner = _current_user("Teacher")
    service = Mock()
    service.get_exam_variant_pair.return_value = ({"header": {}}, {
        "exam_code": "Đề 101", "questions": [{"order": 1, "content_snapshot": {"content": "Câu hỏi", "question_data": {}}}],
    })
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[require_exam_manager] = lambda: owner
    app.dependency_overrides[get_exam_variant_service] = lambda: service
    try:
        response = TestClient(app).get("/api/v1/exams/exam/variants/variant/export/docx")
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
    assert response.status_code == 200
    assert response.content.startswith(b"PK")
    assert "filename*=UTF-8''%C4%90%E1%BB%81%20101_de.docx" in response.headers["Content-Disposition"]
