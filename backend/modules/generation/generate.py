import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from core.config import settings
from core.dependencies import CurrentUser, require_teacher_or_admin
from modules.generation.mongodb import (
    create_generation_job,
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


async def process_generate_background(job_id: str, requested_by_user_id=None):
    """Worker xử lý sinh câu hỏi ngầm."""
    job = get_generation_job(job_id)
    if not job:
        logger.error("Job [%s] không tìm thấy", job_id)
        return

    try:
        logger.info("Job [%s] đang đợi cấp phát tài nguyên sinh câu hỏi...", job_id)

        async with generate_semaphore:
            update_generation_job(job_id, status="processing")
            req = QuestionGenerateRequest(**job["request"])
            result = await generate_questions_rag(req, requested_by_user_id=requested_by_user_id)
            update_generation_job(
                job_id,
                status="completed",
                result={
                    "status": result.status,
                    "data": [item.model_dump() for item in result.data],
                    "summary": [item.model_dump() for item in result.summary],
                },
            )
            logger.info("Job [%s] hoàn tất thành công", job_id)
    except Exception as ex:
        logger.error("Job [%s] thất bại: %s", job_id, ex)
        update_generation_job(job_id, status="failed", error_message=str(ex))


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
):
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
async def get_generation_job_status(job_id: str):
    job = get_generation_job(job_id)
    if not job:
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

    if job["status"] == GenerationJobStatus.FAILED.value and job.get("error_message"):
        response_kwargs["error_message"] = job["error_message"]

    return GenerationJobStatusResponse(**response_kwargs)
