import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from core.config import settings
from core.dependencies import (
    CurrentUser,
    require_teacher_or_admin,
    require_teacher_reviewer_or_admin,
)
from modules.questions.schemas import (
    QuestionCreateRequest,
    QuestionListResponse,
    QuestionResponse,
    QuestionSharingRequest,
    QuestionSourceViewerResponse,
    QuestionVersionResponse,
    QuestionUpdateRequest,
)
from modules.questions.service import QuestionService, get_question_service
from modules.notifications.service import safe_notify_question_resubmitted
from modules.questions.workflow_service import (
    QuestionWorkflowService,
    get_workflow_service,
)

router = APIRouter(prefix=f"{settings.api_prefix}/questions", tags=["Questions"])
logger = logging.getLogger(__name__)


@router.get("", response_model=QuestionListResponse)
def list_questions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    review_status: str | None = Query(None),
    search: str | None = Query(None),
    question_type: str | None = Query(None),
    bloom_level: int | None = Query(None, ge=1, le=6),
    document_id: str | None = Query(None),
    subject_id: str | None = Query(None),
    chapter_id: str | None = Query(None),
    clo_id: str | None = Query(None),
    difficulty: str | None = Query(None),
    quality_color: str | None = Query(None),
    min_score: float | None = Query(None, ge=0, le=1),
    publication_status: str | None = Query(None),
    evaluation_status: str | None = Query(None),
    assignment_status: str | None = Query(None),
    assigned_to: str | None = Query(None),
    creator_user_id: str | None = Query(None),
    waiting_hours_min: float | None = Query(None, ge=0),
    overdue_only: bool = Query(False),
    created_from: datetime | None = Query(None),
    created_to: datetime | None = Query(None),
    submitted_from: datetime | None = Query(None),
    submitted_to: datetime | None = Query(None),
    include_status_counts: bool = Query(False),
    sort_by: str = Query("priority"),
    source_presence: str | None = Query(None),
    secondary_status: str | None = Query(None),
    current_user: CurrentUser = Depends(require_teacher_reviewer_or_admin),
    service: QuestionService = Depends(get_question_service),
):
    try:
        return service.list(
            page,
            page_size,
            review_status,
            search,
            question_type=question_type,
            bloom_level=bloom_level,
            document_id=document_id,
            subject_id=subject_id,
            chapter_id=chapter_id,
            clo_id=clo_id,
            difficulty=difficulty,
            quality_color=quality_color,
            min_score=min_score,
            publication_status=publication_status,
            evaluation_status=evaluation_status,
            assignment_status=assignment_status,
            assigned_to=assigned_to,
            creator_user_id=creator_user_id,
            waiting_hours_min=waiting_hours_min,
            overdue_only=overdue_only,
            created_from=created_from,
            created_to=created_to,
            submitted_from=submitted_from,
            submitted_to=submitted_to,
            include_status_counts=include_status_counts,
            sort_by=sort_by,
            source_presence=source_presence,
            secondary_status=secondary_status,
            current_user=current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("", response_model=QuestionResponse, status_code=status.HTTP_201_CREATED)
def create_question(
    payload: QuestionCreateRequest,
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    service: QuestionService = Depends(get_question_service),
):
    try:
        return service.create(
            payload,
            current_user.id,
            actor_role=current_user.role,
            current_user=current_user,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{question_id}", response_model=QuestionResponse)
def get_question(
    question_id: str,
    current_user: CurrentUser = Depends(require_teacher_reviewer_or_admin),
    service: QuestionService = Depends(get_question_service),
):
    try:
        question = service.get(question_id, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not question:
        raise HTTPException(status_code=404, detail="Không tìm thấy câu hỏi")
    return question


@router.post(
    "/{question_id}/duplicate",
    response_model=QuestionResponse,
    status_code=status.HTTP_201_CREATED,
)
def duplicate_question(
    question_id: str,
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    service: QuestionService = Depends(get_question_service),
):
    try:
        question = service.duplicate(question_id, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not question:
        raise HTTPException(status_code=404, detail="Không tìm thấy câu hỏi")
    return question


@router.get("/{question_id}/versions", response_model=list[QuestionVersionResponse])
def list_question_versions(
    question_id: str,
    current_user: CurrentUser = Depends(require_teacher_reviewer_or_admin),
    service: QuestionService = Depends(get_question_service),
):
    try:
        versions = service.versions(question_id, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if versions is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy câu hỏi")
    return versions


@router.get("/{question_id}/sources", response_model=QuestionSourceViewerResponse)
def get_question_sources(
    question_id: str,
    current_user: CurrentUser = Depends(require_teacher_reviewer_or_admin),
    service: QuestionService = Depends(get_question_service),
):
    try:
        sources = service.source_viewer(question_id, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not sources:
        raise HTTPException(status_code=404, detail="Không tìm thấy câu hỏi")
    return sources


@router.get("/{question_id}/source-pdf")
def get_question_source_pdf(
    question_id: str,
    current_user: CurrentUser = Depends(require_teacher_reviewer_or_admin),
    service: QuestionService = Depends(get_question_service),
):
    try:
        artifact = service.source_pdf_artifact(question_id, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not artifact:
        raise HTTPException(status_code=404, detail="Không tìm thấy PDF nguồn")
    path = artifact["path"]
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="File PDF nguồn không còn tồn tại")
    return FileResponse(
        path,
        media_type=artifact["mime_type"],
        filename=artifact["filename"],
    )


@router.patch("/{question_id}", response_model=QuestionResponse)
def update_question(
    question_id: str,
    payload: QuestionUpdateRequest,
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    service: QuestionService = Depends(get_question_service),
):
    try:
        question = service.update(
            question_id,
            payload,
            current_user.id,
            actor_role=current_user.role,
            current_user=current_user,
        )
    except RuntimeError as exc:
        if str(exc) == "VERSION_CONFLICT":
            raise HTTPException(status_code=409, detail="Câu hỏi đã được cập nhật bởi người khác") from exc
        raise
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not question:
        raise HTTPException(status_code=404, detail="Không tìm thấy câu hỏi")
    return question


@router.patch("/{question_id}/sharing", response_model=QuestionResponse)
def update_question_sharing(
    question_id: str,
    payload: QuestionSharingRequest,
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    service: QuestionService = Depends(get_question_service),
):
    try:
        question = service.update_sharing(question_id, payload, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not question:
        raise HTTPException(status_code=404, detail="Không tìm thấy câu hỏi")
    return question


@router.post("/{question_id}/submit-review", response_model=QuestionResponse)
def submit_question_for_review(
    question_id: str,
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    service: QuestionService = Depends(get_question_service),
    workflow_service: QuestionWorkflowService = Depends(get_workflow_service),
):
    try:
        previous_question = service.get(question_id, current_user)
        previous_review_status = previous_question.get("review_status") if previous_question else None
        question = service.submit_for_review(question_id, current_user)
        if question:
            if (
                previous_review_status != "PENDING"
                and question.get("evaluation_status") != "PASSED"
            ):
                try:
                    workflow_service.enqueue_auto_evaluation(
                        question_id,
                        expected_version=question["current_version"],
                        requested_by_user_id=current_user.id,
                        evaluator_model_code=settings.evaluation_model_provider,
                        trigger="REVIEW_SUBMISSION",
                    )
                except Exception as evaluation_exc:
                    logger.exception(
                        "Could not enqueue evaluation after review submission for %s",
                        question_id,
                    )
                    try:
                        workflow_service.mark_evaluation_enqueue_error(
                            question_id,
                            expected_version=question["current_version"],
                            evaluator_model_code=settings.evaluation_model_provider,
                            message=str(evaluation_exc),
                        )
                    except Exception:
                        # Submission already succeeded.  A secondary failure
                        # while recording AI state must not turn it into a 500.
                        logger.exception(
                            "Could not persist evaluation enqueue error for %s",
                            question_id,
                        )
                question = service.get(question_id, current_user)
            safe_notify_question_resubmitted(
                database=workflow_service.db,
                question_id=question_id,
                previous_review_status=previous_review_status,
                actor_user_id=current_user.id,
            )
    except RuntimeError as exc:
        if str(exc) == "VERSION_CONFLICT":
            raise HTTPException(status_code=409, detail="Câu hỏi đã được cập nhật bởi người khác") from exc
        raise
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not question:
        raise HTTPException(status_code=404, detail="Không tìm thấy câu hỏi")
    return question


@router.delete("/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_question(
    question_id: str,
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    service: QuestionService = Depends(get_question_service),
):
    try:
        deleted = service.archive(question_id, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Không tìm thấy câu hỏi")
