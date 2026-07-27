from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status

from core.config import settings
from core.dependencies import (
    CurrentUser,
    require_admin,
    require_reviewer_or_admin,
    require_teacher_reviewer_or_admin,
)
from modules.questions.workflow_schemas import (
    AutoEvaluationRequest,
    EvaluationCreateRequest,
    MoodlePublicationRequest,
    ReviewAssignmentRequest,
    ReviewCreateRequest,
)
from modules.questions.workflow_service import (
    QuestionWorkflowService,
    get_workflow_service,
    process_evaluation_job_background,
)

router = APIRouter(prefix=f"{settings.api_prefix}/questions", tags=["Question workflow"])


def _translate_workflow_error(exc: Exception):
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, RuntimeError) and str(exc) == "VERSION_CONFLICT":
        raise HTTPException(status_code=409, detail="Phiên bản câu hỏi đã thay đổi") from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


@router.get("/review-dashboard")
def review_dashboard(
    current_user: CurrentUser = Depends(require_reviewer_or_admin),
    service: QuestionWorkflowService = Depends(get_workflow_service),
):
    try:
        return service.review_dashboard(current_user)
    except Exception as exc:
        _translate_workflow_error(exc)


@router.post("/{question_id}/evaluations", status_code=201)
def evaluate_question(
    question_id: str,
    payload: EvaluationCreateRequest,
    current_user: CurrentUser = Depends(require_reviewer_or_admin),
    service: QuestionWorkflowService = Depends(get_workflow_service),
):
    try:
        return service.evaluate(question_id, payload, current_user.id)
    except Exception as exc:
        _translate_workflow_error(exc)


@router.post("/{question_id}/evaluations/auto", status_code=status.HTTP_202_ACCEPTED)
async def auto_evaluate_question(
    question_id: str,
    payload: AutoEvaluationRequest,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_reviewer_or_admin),
    service: QuestionWorkflowService = Depends(get_workflow_service),
):
    try:
        job = service.enqueue_auto_evaluation(
            question_id,
            expected_version=payload.expected_version,
            requested_by_user_id=current_user.id,
            evaluator_model_code=payload.evaluator_model_code,
            trigger="REVIEWER_REQUEST",
        )
        if job.get("status") == "QUEUED":
            background_tasks.add_task(process_evaluation_job_background, job["_id"])
        return job
    except Exception as exc:
        _translate_workflow_error(exc)


@router.get("/{question_id}/evaluations")
def evaluation_history(
    question_id: str,
    current_user: CurrentUser = Depends(require_teacher_reviewer_or_admin),
    service: QuestionWorkflowService = Depends(get_workflow_service),
):
    try:
        return {"items": service.history(question_id, "evaluations", current_user)}
    except Exception as exc:
        _translate_workflow_error(exc)


@router.post("/{question_id}/reviews", status_code=201)
def review_question(
    question_id: str,
    payload: ReviewCreateRequest,
    current_user: CurrentUser = Depends(require_reviewer_or_admin),
    service: QuestionWorkflowService = Depends(get_workflow_service),
):
    try:
        return service.review(question_id, payload, current_user)
    except Exception as exc:
        _translate_workflow_error(exc)


@router.post("/{question_id}/review-assignment/claim")
def claim_review_question(
    question_id: str,
    current_user: CurrentUser = Depends(require_reviewer_or_admin),
    service: QuestionWorkflowService = Depends(get_workflow_service),
):
    try:
        return service.claim_review(question_id, current_user)
    except Exception as exc:
        _translate_workflow_error(exc)


@router.post("/{question_id}/review-assignment/release")
def release_review_question(
    question_id: str,
    current_user: CurrentUser = Depends(require_reviewer_or_admin),
    service: QuestionWorkflowService = Depends(get_workflow_service),
):
    try:
        return service.release_review(question_id, current_user)
    except Exception as exc:
        _translate_workflow_error(exc)


@router.post("/{question_id}/review-assignment")
def assign_review_question(
    question_id: str,
    payload: ReviewAssignmentRequest,
    current_user: CurrentUser = Depends(require_admin),
    service: QuestionWorkflowService = Depends(get_workflow_service),
):
    try:
        return service.assign_review(question_id, payload, current_user)
    except Exception as exc:
        _translate_workflow_error(exc)


@router.get("/{question_id}/reviews")
def review_history(
    question_id: str,
    current_user: CurrentUser = Depends(require_teacher_reviewer_or_admin),
    service: QuestionWorkflowService = Depends(get_workflow_service),
):
    try:
        return {"items": service.history(question_id, "reviews", current_user)}
    except Exception as exc:
        _translate_workflow_error(exc)


@router.post("/{question_id}/moodle-publications", status_code=201)
def publish_question_to_moodle(
    question_id: str,
    payload: MoodlePublicationRequest,
    current_user: CurrentUser = Depends(require_reviewer_or_admin),
    service: QuestionWorkflowService = Depends(get_workflow_service),
):
    try:
        return service.publish_to_moodle(question_id, payload, current_user.id, current_user.role)
    except Exception as exc:
        _translate_workflow_error(exc)


@router.get("/{question_id}/moodle-publications")
def moodle_publication_history(
    question_id: str,
    current_user: CurrentUser = Depends(require_teacher_reviewer_or_admin),
    service: QuestionWorkflowService = Depends(get_workflow_service),
):
    try:
        return {"items": service.history(question_id, "publications", current_user)}
    except Exception as exc:
        _translate_workflow_error(exc)


@router.get("/{question_id}/moodle-export")
def export_question_to_moodle(
    question_id: str,
    format: str = Query("gift", pattern="^(gift|xml)$"),
    current_user: CurrentUser = Depends(require_teacher_reviewer_or_admin),
    service: QuestionWorkflowService = Depends(get_workflow_service),
):
    try:
        export = service.export_moodle(question_id, format, current_user)
    except Exception as exc:
        _translate_workflow_error(exc)
    return Response(
        content=export["content"],
        media_type=export["media_type"],
        headers={
            "Content-Disposition": f'attachment; filename="{export["filename"]}"',
        },
    )
