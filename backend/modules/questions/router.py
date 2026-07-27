from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

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
    QuestionVersionResponse,
    QuestionUpdateRequest,
)
from modules.questions.service import QuestionService, get_question_service
from modules.questions.workflow_service import (
    DEFAULT_EVALUATOR_MODEL_CODE,
    QuestionWorkflowService,
    get_workflow_service,
    process_evaluation_job_background,
)

router = APIRouter(prefix=f"{settings.api_prefix}/questions", tags=["Questions"])


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
    difficulty: str | None = Query(None),
    quality_color: str | None = Query(None),
    min_score: float | None = Query(None, ge=0, le=1),
    publication_status: str | None = Query(None),
    evaluation_status: str | None = Query(None),
    assignment_status: str | None = Query(None),
    assigned_to: str | None = Query(None),
    current_user: CurrentUser = Depends(require_teacher_reviewer_or_admin),
    service: QuestionService = Depends(get_question_service),
):
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
        difficulty=difficulty,
        quality_color=quality_color,
        min_score=min_score,
        publication_status=publication_status,
        evaluation_status=evaluation_status,
        assignment_status=assignment_status,
        assigned_to=assigned_to,
        current_user=current_user,
    )


@router.post("", response_model=QuestionResponse, status_code=status.HTTP_201_CREATED)
def create_question(
    payload: QuestionCreateRequest,
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    service: QuestionService = Depends(get_question_service),
):
    try:
        return service.create(payload, current_user.id, actor_role=current_user.role)
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


@router.post("/{question_id}/submit-review", response_model=QuestionResponse)
def submit_question_for_review(
    question_id: str,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    service: QuestionService = Depends(get_question_service),
    workflow_service: QuestionWorkflowService = Depends(get_workflow_service),
):
    try:
        question = service.submit_for_review(question_id, current_user)
        if question and question.get("evaluation_status") != "PASSED":
            job = workflow_service.enqueue_auto_evaluation(
                question_id,
                expected_version=question["current_version"],
                requested_by_user_id=current_user.id,
                evaluator_model_code=DEFAULT_EVALUATOR_MODEL_CODE,
                trigger="TEACHER_SUBMIT",
            )
            if job.get("status") == "QUEUED":
                background_tasks.add_task(process_evaluation_job_background, job["_id"])
            question = service.get(question_id, current_user) or question
    except RuntimeError as exc:
        if str(exc) == "VERSION_CONFLICT":
            raise HTTPException(status_code=409, detail="Cau hoi da duoc cap nhat boi nguoi khac") from exc
        raise
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not question:
        raise HTTPException(status_code=404, detail="Khong tim thay cau hoi")
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
