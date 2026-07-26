from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from core.config import settings
from core.dependencies import CurrentUser, require_teacher_or_admin
from modules.exams.pdf_service import VALID_EXPORT_TYPES, render_exam_pdf
from modules.exams.schemas import (
    AddQuestionsManualRequest,
    ExamCreateRequest,
    ExamListResponse,
    ExamMatrixRequest,
    ExamPreviewResponse,
    ExamResponse,
    ExamUpdateRequest,
    ExamVariantCreateRequest,
    ExamVariantResponse,
    MatrixCellAvailability,
)
from modules.exams.service import (
    ExamService,
    ExamVariantService,
    get_exam_service,
    get_exam_variant_service,
)

router = APIRouter(prefix=f"{settings.api_prefix}/exams", tags=["Exams"])


def _translate(exc: Exception):
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


@router.post("", response_model=ExamResponse, status_code=status.HTTP_201_CREATED)
def create_exam(
    payload: ExamCreateRequest,
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    service: ExamService = Depends(get_exam_service),
):
    try:
        return service.create_exam(payload, current_user.id)
    except Exception as exc:
        _translate(exc)


@router.get("", response_model=ExamListResponse)
def list_exams(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    service: ExamService = Depends(get_exam_service),
):
    return service.list_exams(page, page_size, current_user)


@router.get("/{exam_id}", response_model=ExamResponse)
def get_exam(
    exam_id: str,
    _user: CurrentUser = Depends(require_teacher_or_admin),
    service: ExamService = Depends(get_exam_service),
):
    try:
        return service.get_exam(exam_id)
    except Exception as exc:
        _translate(exc)


@router.patch("/{exam_id}", response_model=ExamResponse)
def update_exam(
    exam_id: str,
    payload: ExamUpdateRequest,
    _user: CurrentUser = Depends(require_teacher_or_admin),
    service: ExamService = Depends(get_exam_service),
):
    try:
        return service.update_exam(exam_id, payload)
    except Exception as exc:
        _translate(exc)


@router.delete("/{exam_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_exam(
    exam_id: str,
    _user: CurrentUser = Depends(require_teacher_or_admin),
    service: ExamService = Depends(get_exam_service),
):
    try:
        service.delete_exam(exam_id)
    except Exception as exc:
        _translate(exc)


@router.put("/{exam_id}/matrix", response_model=ExamResponse)
def save_matrix(
    exam_id: str,
    payload: ExamMatrixRequest,
    _user: CurrentUser = Depends(require_teacher_or_admin),
    service: ExamService = Depends(get_exam_service),
):
    try:
        return service.save_matrix(exam_id, payload)
    except Exception as exc:
        _translate(exc)


@router.get("/{exam_id}/matrix/availability", response_model=list[MatrixCellAvailability])
def matrix_availability(
    exam_id: str,
    _user: CurrentUser = Depends(require_teacher_or_admin),
    service: ExamService = Depends(get_exam_service),
):
    try:
        return service.matrix_availability(exam_id)
    except Exception as exc:
        _translate(exc)


@router.post("/{exam_id}/questions/auto-generate", response_model=ExamResponse)
def auto_generate_questions(
    exam_id: str,
    _user: CurrentUser = Depends(require_teacher_or_admin),
    service: ExamService = Depends(get_exam_service),
):
    try:
        return service.auto_generate_pool(exam_id)
    except Exception as exc:
        _translate(exc)


@router.post("/{exam_id}/questions", response_model=ExamResponse)
def add_questions_manual(
    exam_id: str,
    payload: AddQuestionsManualRequest,
    _user: CurrentUser = Depends(require_teacher_or_admin),
    service: ExamService = Depends(get_exam_service),
):
    try:
        return service.add_questions_manual(exam_id, payload)
    except Exception as exc:
        _translate(exc)


@router.delete("/{exam_id}/questions/{question_id}", response_model=ExamResponse)
def remove_question(
    exam_id: str,
    question_id: str,
    _user: CurrentUser = Depends(require_teacher_or_admin),
    service: ExamService = Depends(get_exam_service),
):
    try:
        return service.remove_question(exam_id, question_id)
    except Exception as exc:
        _translate(exc)


@router.post(
    "/{exam_id}/variants",
    response_model=ExamVariantResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_variant(
    exam_id: str,
    payload: ExamVariantCreateRequest,
    _user: CurrentUser = Depends(require_teacher_or_admin),
    service: ExamVariantService = Depends(get_exam_variant_service),
):
    try:
        return service.create_variant(exam_id, payload)
    except Exception as exc:
        _translate(exc)


@router.get("/{exam_id}/variants", response_model=list[ExamVariantResponse])
def list_variants(
    exam_id: str,
    _user: CurrentUser = Depends(require_teacher_or_admin),
    service: ExamVariantService = Depends(get_exam_variant_service),
):
    try:
        return service.list_variants(exam_id)
    except Exception as exc:
        _translate(exc)


@router.get("/{exam_id}/variants/{variant_id}", response_model=ExamVariantResponse)
def get_variant(
    exam_id: str,
    variant_id: str,
    _user: CurrentUser = Depends(require_teacher_or_admin),
    service: ExamVariantService = Depends(get_exam_variant_service),
):
    try:
        return service.get_variant(exam_id, variant_id)
    except Exception as exc:
        _translate(exc)


@router.delete(
    "/{exam_id}/variants/{variant_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_variant(
    exam_id: str,
    variant_id: str,
    _user: CurrentUser = Depends(require_teacher_or_admin),
    service: ExamVariantService = Depends(get_exam_variant_service),
):
    try:
        service.delete_variant(exam_id, variant_id)
    except Exception as exc:
        _translate(exc)


@router.get("/{exam_id}/variants/{variant_id}/preview", response_model=ExamPreviewResponse)
def preview_variant(
    exam_id: str,
    variant_id: str,
    _user: CurrentUser = Depends(require_teacher_or_admin),
    service: ExamVariantService = Depends(get_exam_variant_service),
):
    try:
        return service.build_preview(exam_id, variant_id)
    except Exception as exc:
        _translate(exc)


@router.get("/{exam_id}/variants/{variant_id}/export/pdf")
async def export_variant_pdf(
    exam_id: str,
    variant_id: str,
    export_type: str = Query("de", alias="type"),
    _user: CurrentUser = Depends(require_teacher_or_admin),
    service: ExamVariantService = Depends(get_exam_variant_service),
):
    if export_type not in VALID_EXPORT_TYPES:
        raise HTTPException(status_code=400, detail="type phải là de, dapan hoặc de_dapan")
    try:
        exam = service.exams.find(exam_id)
        if not exam:
            raise LookupError("Không tìm thấy đề thi")
        variant = service.variants.find(variant_id)
        if not variant or str(variant["exam_id"]) != exam_id:
            raise LookupError("Không tìm thấy mã đề")
    except Exception as exc:
        _translate(exc)
    if not variant["questions"]:
        raise HTTPException(status_code=400, detail="Mã đề chưa có câu hỏi, không thể xuất PDF")
    pdf_bytes = await render_exam_pdf(
        exam["header"], variant["exam_code"], variant["questions"], export_type
    )
    filename = f"{variant['exam_code']}_{export_type}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
