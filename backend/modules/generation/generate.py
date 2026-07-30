import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from core.config import settings
from core.dependencies import CurrentUser, require_teacher_or_admin
from modules.documents.service import DocumentService, get_document_service
from modules.generation.mongodb import (
    create_generation_job,
    generation_job_has_status,
    get_generation_job,
    update_generation_job,
)
from modules.generation.question import generate_questions_rag
from modules.generation.schemas import (
    GenerationJobStatus,
    GenerationJobStatusResponse,
    GenerationPlanSummary,
    GeneratedQuestion,
    JobAcceptedResponse,
    QuestionGenerateRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix=f"{settings.api_prefix}/generate", tags=["generation"])

generate_semaphore = asyncio.Semaphore(1)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def elapsed_ms(start: datetime | None, end: datetime | None = None) -> int | None:
    if not start:
        return None
    end = end or utc_now()
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return max(0, int((end - start).total_seconds() * 1000))


def build_generation_metrics(
    job: dict,
    *,
    processing_started_at: datetime | None,
    finished_at: datetime,
    client_telemetry: dict | None,
) -> dict:
    created_at = job.get("created_at")
    server = {
        "queued_ms": elapsed_ms(created_at, processing_started_at),
        "processing_ms": elapsed_ms(processing_started_at, finished_at),
        "total_ms": elapsed_ms(created_at, finished_at),
        "created_at": created_at,
        "processing_started_at": processing_started_at,
        "finished_at": finished_at,
    }
    client = client_telemetry or {}
    client_pre_generate = client.get("elapsed_before_generate_ms")
    estimated_total = None
    if isinstance(client_pre_generate, int) and server["processing_ms"] is not None:
        estimated_total = client_pre_generate + server["processing_ms"]
    return {
        "server": server,
        "client": client,
        "summary": {
            "estimated_frontend_total_ms": estimated_total,
            "has_client_pipeline_timings": bool(client),
        },
    }


async def process_generate_background(job_id: str, requested_by_user_id=None):
    """Worker xử lý sinh câu hỏi ngầm."""
    job = get_generation_job(job_id)
    if not job:
        logger.error("Job [%s] không tìm thấy", job_id)
        return
    processing_started_at = None
    client_telemetry = (job.get("request") or {}).get("client_telemetry") or {}

    try:
        logger.info("Job [%s] đang đợi cấp phát tài nguyên sinh câu hỏi...", job_id)

        async with generate_semaphore:
            processing_started_at = utc_now()
            claimed_job = update_generation_job(
                job_id,
                status="processing",
                expected_status="queued",
            )
            if not claimed_job:
                logger.info("Job [%s] không còn ở hàng đợi; bỏ qua xử lý", job_id)
                return
            req = QuestionGenerateRequest(**job["request"])
            client_telemetry = (
                req.client_telemetry.model_dump(exclude_none=True)
                if req.client_telemetry
                else {}
            )
            result = await generate_questions_rag(
                req,
                requested_by_user_id=requested_by_user_id,
                should_continue=lambda: generation_job_has_status(job_id, "processing"),
            )
            finished_at = utc_now()
            metrics = build_generation_metrics(
                job,
                processing_started_at=processing_started_at,
                finished_at=finished_at,
                client_telemetry=client_telemetry,
            )
            completed_job = update_generation_job(
                job_id,
                status="completed",
                result={
                    "status": result.status,
                    "data": [item.model_dump() for item in result.data],
                    "summary": [item.model_dump() for item in result.summary],
                },
                metrics=metrics,
                expected_status="processing",
            )
            if completed_job:
                logger.info("Job [%s] hoàn tất thành công", job_id)
            else:
                logger.info("Job [%s] đã kết thúc trước khi worker hoàn tất", job_id)
    except Exception as ex:
        logger.error("Job [%s] thất bại: %s", job_id, ex)
        metrics = build_generation_metrics(
            job,
            processing_started_at=processing_started_at,
            finished_at=utc_now(),
            client_telemetry=client_telemetry,
        )
        failed_job = update_generation_job(
            job_id,
            status="failed",
            metrics=metrics,
            error_message=str(ex),
            expected_status="processing",
        )
        if not failed_job:
            logger.info("Giữ nguyên trạng thái kết thúc hiện tại của job [%s]", job_id)


@router.post(
    "/questions",
    response_model=JobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Đưa yêu cầu sinh câu hỏi vào hàng đợi",
)
async def api_generate_questions(
    req: QuestionGenerateRequest,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    document_service: DocumentService = Depends(get_document_service),
):
    try:
        if not document_service.can_use(req.document_id, current_user):
            raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job_id = create_generation_job(req.model_dump(mode="json"), requested_by_user_id=current_user.id)
    background_tasks.add_task(
        process_generate_background,
        job_id=job_id,
        requested_by_user_id=current_user.id,
    )

    return JobAcceptedResponse(
        job_id=job_id,
        status=GenerationJobStatus.QUEUED,
        message="Yêu cầu sinh câu hỏi đã được đưa vào hàng đợi.",
    )


@router.get(
    "/status/{job_id}",
    response_model=GenerationJobStatusResponse,
    summary="Kiểm tra trạng thái job sinh câu hỏi",
)
async def get_generation_job_status(
    job_id: str,
    current_user: CurrentUser = Depends(require_teacher_or_admin),
):
    job = get_generation_job(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy Job ID này trong hệ thống",
        )
    if (
        current_user.role != "Admin"
        and str(job.get("requested_by_user_id")) != str(current_user.id)
    ):
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy Job ID này trong hệ thống",
        )

    response_kwargs = {
        "job_id": job["job_id"],
        "status": job["status"],
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
    }

    if job["status"] == GenerationJobStatus.COMPLETED.value and job.get("result"):
        result_data = job["result"].get("data", [])
        response_kwargs["data"] = [GeneratedQuestion(**item) for item in result_data]
        result_summary = job["result"].get("summary", [])
        response_kwargs["summary"] = [GenerationPlanSummary(**item) for item in result_summary]

    if job.get("metrics"):
        response_kwargs["metrics"] = job["metrics"]

    if job["status"] == GenerationJobStatus.FAILED.value and job.get("error_message"):
        response_kwargs["error_message"] = job["error_message"]

    return GenerationJobStatusResponse(**response_kwargs)
