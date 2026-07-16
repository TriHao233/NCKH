import os
import logging
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks

from modules.ocr import service

router = APIRouter(prefix="/api/v1/ocr", tags=["OCR"])
logger = logging.getLogger(__name__)


# -------------------------------------------------------------
# API: Upload File (Trả về ngay lập tức)
# -------------------------------------------------------------
@router.post("/upload", summary="Upload file PDF và đưa vào hàng đợi OCR")
async def upload_pdf(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Chỉ chấp nhận file .pdf")

    file.file.seek(0, os.SEEK_END)
    file_size = file.file.tell()
    file.file.seek(0)

    if file_size > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Dung lượng tối đa 50MB")

    try:
        job = service.create_upload_job(file.filename, file.file)
    except Exception:
        raise HTTPException(status_code=500, detail="Lỗi lưu file xuống đĩa")
    finally:
        file.file.close()

    # Kích hoạt Background Task
    background_tasks.add_task(
        service.process_ocr_background,
        job_id=job["job_id"],
        upload_path=job["upload_path"],
        output_path=job["output_path"],
        document_title=job["title"]
    )

    return {
        "message": "File đã được tiếp nhận và đang xử lý ngầm.",
        "job_id": job["job_id"],
        "status": "queued"
    }


# -------------------------------------------------------------
# API: Truy vấn trạng thái (Dành cho Frontend hỏi thăm tiến độ)
# -------------------------------------------------------------
@router.get("/status/{job_id}", summary="Kiểm tra trạng thái tiến trình OCR")
async def check_job_status(job_id: str):
    doc = service.get_job_status(job_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Không tìm thấy Job ID này trong hệ thống")
    return doc
