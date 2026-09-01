import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from core.config import settings
from core.dependencies import CurrentUser, has_permission, require_teacher_or_admin
from core.job_worker import maintain_lease
from modules.documents.service import DocumentService, get_document_service
from modules.generation.mongodb import (
    claim_generation_job,
    count_active_generation_jobs,
    create_generation_job,
    get_generation_job,
    get_generation_job_by_idempotency,
    heartbeat_generation_job,
    retry_or_dead_letter_generation_job,
    update_generation_job,
    update_generation_progress,
)
from modules.generation.question import generate_questions_rag
from modules.generation.llm.model_registry import GENERATION_CAPABILITY, resolve_model_snapshot
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


async def process_generate_background(job_id: str, worker_id: str):
    """Worker xử lý sinh câu hỏi ngầm."""
    job = await asyncio.to_thread(claim_generation_job, job_id, worker_id)
    if not job:
        logger.info("Job [%s] không còn ở trạng thái queued", job_id)
        return
    requested_by_user_id = job.get("requested_by_user_id")
    processing_started_at = None
    client_telemetry = (job.get("request") or {}).get("client_telemetry") or {}
    lease_stop = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        maintain_lease(
            lambda: heartbeat_generation_job(job_id, worker_id),
            lease_stop,
        )
    )

    try:
        logger.info("Job [%s] đang đợi cấp phát tài nguyên sinh câu hỏi...", job_id)

        async with generate_semaphore:
            processing_started_at = utc_now()
            req = QuestionGenerateRequest(**job["request"])
            client_telemetry = (
                req.client_telemetry.model_dump(exclude_none=True)
                if req.client_telemetry
                else {}
            )

            async def report_progress(progress: dict) -> None:
                await asyncio.to_thread(update_generation_progress, job_id, worker_id, progress)

            result = await generate_questions_rag(
                req,
                requested_by_user_id=requested_by_user_id,
                progress_callback=report_progress,
                model_snapshot=job.get("model_snapshot"),
                code_model_snapshot=job.get("code_model_snapshot"),
                fallback_model_snapshot=job.get("fallback_model_snapshot"),
            )
            finished_at = utc_now()
            metrics = build_generation_metrics(
                job,
                processing_started_at=processing_started_at,
                finished_at=finished_at,
                client_telemetry=client_telemetry,
            )
            await asyncio.to_thread(
                update_generation_job,
                job_id,
                status="completed",
                result={
                    "status": result.status,
                    "data": [item.model_dump() for item in result.data],
                    "summary": [item.model_dump() for item in result.summary],
                },
                metrics=metrics,
                worker_id=worker_id,
            )
            logger.info("Job [%s] hoàn tất thành công", job_id)
    except Exception as ex:
        logger.exception("Job [%s] thất bại: %s", job_id, ex)
        metrics = build_generation_metrics(
            job,
            processing_started_at=processing_started_at,
            finished_at=utc_now(),
            client_telemetry=client_telemetry,
        )
        next_status = await asyncio.to_thread(
            retry_or_dead_letter_generation_job,
            job,
            worker_id,
            error_message=str(ex),
            metrics=metrics,
        )
        logger.info("Job [%s] moved to %s", job_id, next_status)
    finally:
        lease_stop.set()
        await heartbeat_task


@router.post(
    "/questions",
    response_model=JobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Đưa yêu cầu sinh câu hỏi vào hàng đợi",
)
async def api_generate_questions(
    req: QuestionGenerateRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=128),
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    document_service: DocumentService = Depends(get_document_service),
):
    try:
        if not await asyncio.to_thread(document_service.can_use, req.document_id, current_user):
            raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    normalized_key = idempotency_key.strip() if idempotency_key else None
    if normalized_key:
        existing = await asyncio.to_thread(
            get_generation_job_by_idempotency,
            current_user.id,
            normalized_key,
        )
        if existing:
            return JobAcceptedResponse(
                job_id=existing["job_id"],
                status=existing["status"],
                message="Yêu cầu trùng đã được ánh xạ về job hiện có.",
            )
    active_count = await asyncio.to_thread(count_active_generation_jobs, current_user.id)
    if active_count >= settings.max_active_generation_jobs_per_user:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Bạn đã đạt giới hạn generation job đang chờ hoặc đang xử lý.",
            headers={"Retry-After": "15"},
        )
    try:
        model_snapshot = await asyncio.to_thread(
            resolve_model_snapshot,
            req.model_provider,
            capability=GENERATION_CAPABILITY,
        )
        code_model_snapshot = (
            model_snapshot
            if req.code_model_provider == req.model_provider
            else await asyncio.to_thread(
                resolve_model_snapshot,
                req.code_model_provider,
                capability=GENERATION_CAPABILITY,
            )
        )
        fallback_snapshot = None
        if settings.generation_fallback_provider:
            fallback_snapshot = await asyncio.to_thread(
                resolve_model_snapshot,
                settings.generation_fallback_provider,
                capability=GENERATION_CAPABILITY,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job_id = await asyncio.to_thread(
        create_generation_job,
        req.model_dump(mode="json"),
        current_user.id,
        normalized_key,
        model_snapshot=model_snapshot,
        code_model_snapshot=code_model_snapshot,
        fallback_model_snapshot=fallback_snapshot,
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
    can_manage_all = current_user.role == "Admin" or has_permission(current_user, "questions.manage_all")
    owner_id = None if can_manage_all else current_user.id
    job = await asyncio.to_thread(get_generation_job, job_id, requested_by_user_id=owner_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy Job ID này trong hệ thống",
        )

    return _build_generation_status_response(job)


def _build_generation_status_response(job: dict) -> GenerationJobStatusResponse:
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
    if job.get("progress"):
        response_kwargs["progress"] = job["progress"]
    if job.get("model_snapshot"):
        snapshot = job["model_snapshot"]
        response_kwargs["model"] = {
            "code": snapshot.get("model_code"),
            "name": snapshot.get("display_name") or snapshot.get("model_name"),
            "version": snapshot.get("model_name"),
            "runtime": snapshot.get("runtime"),
        }

    if job["status"] == GenerationJobStatus.FAILED.value and job.get("error_message"):
        response_kwargs["error_message"] = job["error_message"]

    return GenerationJobStatusResponse(**response_kwargs)


@router.get(
    "/status/{job_id}/events",
    summary="Theo dõi tiến độ job sinh câu hỏi qua Server-Sent Events",
)
async def stream_generation_job_status(
    job_id: str,
    request: Request,
    current_user: CurrentUser = Depends(require_teacher_or_admin),
):
    can_manage_all = current_user.role == "Admin" or has_permission(current_user, "questions.manage_all")
    owner_id = None if can_manage_all else current_user.id
    initial_job = await asyncio.to_thread(get_generation_job, job_id, requested_by_user_id=owner_id)
    if not initial_job:
        raise HTTPException(status_code=404, detail="Không tìm thấy Job ID này trong hệ thống")

    async def event_stream():
        last_version = None
        heartbeat_deadline = asyncio.get_running_loop().time() + 15
        while not await request.is_disconnected():
            job = await asyncio.to_thread(get_generation_job, job_id, requested_by_user_id=owner_id)
            if not job:
                yield 'event: error\ndata: {"detail":"Job không còn tồn tại"}\n\n'
                return
            version = (job.get("updated_at"), job.get("status"), json.dumps(job.get("progress"), sort_keys=True))
            now = asyncio.get_running_loop().time()
            if version != last_version:
                payload = _build_generation_status_response(job).model_dump_json()
                yield f"event: status\ndata: {payload}\n\n"
                last_version = version
                heartbeat_deadline = now + 15
            elif now >= heartbeat_deadline:
                yield ": keep-alive\n\n"
                heartbeat_deadline = now + 15
            if job.get("status") in {"completed", "failed"}:
                return
            await asyncio.sleep(1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
