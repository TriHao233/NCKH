from fastapi import APIRouter, Depends, HTTPException

from core.config import settings
from core.dependencies import CurrentUser, require_teacher_or_admin
from modules.questions.workflow_schemas import EvaluationCreateRequest, ReviewCreateRequest
from modules.questions.workflow_service import QuestionWorkflowService, get_workflow_service

router = APIRouter(prefix=f"{settings.api_prefix}/questions", tags=["Question workflow"])


def _translate_workflow_error(exc: Exception):
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, RuntimeError) and str(exc) == "VERSION_CONFLICT":
        raise HTTPException(status_code=409, detail="Phiên bản câu hỏi đã thay đổi") from exc
    raise exc


@router.post("/{question_id}/evaluations", status_code=201)
def evaluate_question(
    question_id: str,
    payload: EvaluationCreateRequest,
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    service: QuestionWorkflowService = Depends(get_workflow_service),
):
    try:
        return service.evaluate(question_id, payload, current_user.id)
    except Exception as exc:
        _translate_workflow_error(exc)


@router.get("/{question_id}/evaluations")
def evaluation_history(
    question_id: str,
    _user: CurrentUser = Depends(require_teacher_or_admin),
    service: QuestionWorkflowService = Depends(get_workflow_service),
):
    try:
        return {"items": service.history(question_id, "evaluations")}
    except Exception as exc:
        _translate_workflow_error(exc)


@router.post("/{question_id}/reviews", status_code=201)
def review_question(
    question_id: str,
    payload: ReviewCreateRequest,
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    service: QuestionWorkflowService = Depends(get_workflow_service),
):
    try:
        return service.review(question_id, payload, current_user.id)
    except Exception as exc:
        _translate_workflow_error(exc)


@router.get("/{question_id}/reviews")
def review_history(
    question_id: str,
    _user: CurrentUser = Depends(require_teacher_or_admin),
    service: QuestionWorkflowService = Depends(get_workflow_service),
):
    try:
        return {"items": service.history(question_id, "reviews")}
    except Exception as exc:
        _translate_workflow_error(exc)
