import asyncio
import hashlib
import logging
import os
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from core.config import resolve_path, settings
from core.dependencies import CurrentUser, require_teacher_or_admin
from modules.documents.service import DocumentService, get_document_service
from modules.ocr.mongodb import (
    attach_original_artifact,
    create_document_record,
    create_ocr_job,
    get_document_status,
    save_document_pages,
    update_document_status,
)
from modules.ocr.pipeline import run_ocr_pipeline

router = APIRouter(prefix=f"{settings.api_prefix}/ocr", tags=["OCR"])
logger = logging.getLogger(__name__)
gpu_semaphore = asyncio.Semaphore(1)

_UPLOAD_DIR = resolve_path(settings.upload_dir)
_OUTPUT_DIR = resolve_path(settings.ocr_output_dir)
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def process_ocr_background(
    document_id: str,
    job_id: str,
    upload_path: str,
    output_path: str,
    document_title: str,
):
    try:
        async with gpu_semaphore:
            update_document_status(document_id, job_id, status="processing")
            started_at = time.time()
            result = await run_in_threadpool(
                run_ocr_pipeline,
                pdf_path=upload_path,
                output_path=output_path,
                document_title=document_title,
            )
            stats = result["stats"]
            stats["processing_time"] = round(time.time() - started_at, 1)
            save_document_pages(document_id, job_id, result["pages"])
            update_document_status(document_id, job_id, status="completed", stats=stats)
    except Exception as exc:
        logger.exception("OCR job %s failed", job_id)
        update_document_status(
            document_id,
            job_id,
            status="failed",
            error_message=str(exc),
        )


async def queue_pdf_ocr_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    current_user: CurrentUser,
    *,
    subject_id: str | None = None,
    chapter_id: str | None = None,
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Chỉ chấp nhận file PDF")

    file.file.seek(0, os.SEEK_END)
    file_size = file.file.tell()
    file.file.seek(0)
    if file_size > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Dung lượng tối đa 50 MB")

    title = Path(file.filename).stem.replace("_", " ")
    document_id = create_document_record(
        filename=file.filename,
        title=title,
        uploaded_by_user_id=current_user.id,
        subject_id=subject_id,
        chapter_id=chapter_id,
    )
    job_id = create_ocr_job(document_id)
    upload_path = _UPLOAD_DIR / f"{document_id}_{file.filename}"
    output_path = _OUTPUT_DIR / f"{document_id}_result.md"

    try:
        with upload_path.open("wb") as destination:
            shutil.copyfileobj(file.file, destination)
        digest = hashlib.sha256()
        with upload_path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        attach_original_artifact(
            document_id,
            uri=str(upload_path),
            size_bytes=file_size,
            sha256=digest.hexdigest(),
        )
    except Exception as exc:
        update_document_status(
            document_id,
            job_id,
            status="failed",
            error_message="Lỗi lưu file vật lý",
        )
        raise HTTPException(status_code=500, detail="Lỗi lưu file") from exc
    finally:
        file.file.close()

    background_tasks.add_task(
        process_ocr_background,
        document_id=document_id,
        job_id=job_id,
        upload_path=str(upload_path),
        output_path=str(output_path),
        document_title=title,
    )
    return {
        "message": "File đã được tiếp nhận và đang xử lý nền",
        "document_id": document_id,
        "job_id": job_id,
        "status": "QUEUED",
    }

@router.post("/upload", summary="Compatibility upload route; prefer /documents/upload")
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    subject_id: str | None = Form(None),
    chapter_id: str | None = Form(None),
    current_user: CurrentUser = Depends(require_teacher_or_admin),
):
    return await queue_pdf_ocr_upload(
        background_tasks,
        file,
        current_user,
        subject_id=subject_id,
        chapter_id=chapter_id,
    )


@router.get("/status/{job_id}", summary="Get OCR job status")
def check_job_status(
    job_id: str,
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    document_service: DocumentService = Depends(get_document_service),
):
    try:
        result = get_document_status(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=404, detail="Không tìm thấy OCR job")
    document = result.get("document")
    if document:
        try:
            document_service.can_use(document["id"], current_user)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
    job = result["job"]
    return {
        "job_id": job["_id"],
        "document_id": job["document_id"],
        "status": job["status"].lower(),
        "progress": job.get("progress"),
        "error_message": (job.get("error") or {}).get("message"),
        "stats": job.get("stats"),
    }
