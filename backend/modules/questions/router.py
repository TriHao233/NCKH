from fastapi import APIRouter, Depends, HTTPException, Query, status

from core.config import settings
from core.dependencies import CurrentUser, require_teacher_or_admin
from modules.questions.schemas import (
    QuestionCreateRequest,
    QuestionListResponse,
    QuestionResponse,
    QuestionUpdateRequest,
)
from modules.questions.service import QuestionService, get_question_service

router = APIRouter(prefix=f"{settings.api_prefix}/questions", tags=["Questions"])


@router.get("", response_model=QuestionListResponse)
def list_questions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    review_status: str | None = None,
    search: str | None = None,
    _user: CurrentUser = Depends(require_teacher_or_admin),
    service: QuestionService = Depends(get_question_service),
):
    return service.list(page, page_size, review_status, search)


@router.post("", response_model=QuestionResponse, status_code=status.HTTP_201_CREATED)
def create_question(
    payload: QuestionCreateRequest,
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    service: QuestionService = Depends(get_question_service),
):
    try:
        return service.create(payload, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{question_id}", response_model=QuestionResponse)
def get_question(
    question_id: str,
    _user: CurrentUser = Depends(require_teacher_or_admin),
    service: QuestionService = Depends(get_question_service),
):
    try:
        question = service.get(question_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not question:
        raise HTTPException(status_code=404, detail="Không tìm thấy câu hỏi")
    return question


@router.patch("/{question_id}", response_model=QuestionResponse)
def update_question(
    question_id: str,
    payload: QuestionUpdateRequest,
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    service: QuestionService = Depends(get_question_service),
):
    try:
        question = service.update(question_id, payload, current_user.id)
    except RuntimeError as exc:
        if str(exc) == "VERSION_CONFLICT":
            raise HTTPException(status_code=409, detail="Câu hỏi đã được cập nhật bởi người khác") from exc
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not question:
        raise HTTPException(status_code=404, detail="Không tìm thấy câu hỏi")
    return question


@router.delete("/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_question(
    question_id: str,
    _user: CurrentUser = Depends(require_teacher_or_admin),
    service: QuestionService = Depends(get_question_service),
):
    try:
        deleted = service.archive(question_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Không tìm thấy câu hỏi")
