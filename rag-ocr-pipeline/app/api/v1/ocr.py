import os
import shutil
import time
import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.concurrency import run_in_threadpool

from app.services.ocr.pipeline import run_ocr_pipeline

from app.db.mongodb import create_document_record, update_document_status, save_document_pages, get_document_status

router = APIRouter(prefix="/api/v1/ocr", tags=["OCR"])
logger = logging.getLogger(__name__)

gpu_semaphore = asyncio.Semaphore(1)

_BASE_DIR = Path(__file__).resolve().parents[3]
_UPLOAD_DIR = _BASE_DIR / "data" / "uploads"
_OUTPUT_DIR = _BASE_DIR / "data" / "ocr_outputs"
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# -------------------------------------------------------------
# WORKER: Hàm xử lý ngầm (Background Task)
# -------------------------------------------------------------
async def process_ocr_background(job_id: str, upload_path: str, output_path: str, document_title: str):
    try:
        logger.info(f"Job [{job_id}] đang đợi cấp phát GPU...")
        
        async with gpu_semaphore:
            logger.info(f"Job [{job_id}] đã vào GPU. Cập nhật trạng thái -> processing")
            update_document_status(job_id, status="processing")
            
            start_time = time.time()
            
            # Chạy OCR Pipeline ở luồng riêng
            result = await run_in_threadpool(
                run_ocr_pipeline,
                pdf_path=upload_path, 
                output_path=output_path, 
                document_title=document_title
            )
            
            elapsed = round(time.time() - start_time, 1)
            stats_data = result["stats"]
            stats_data["processing_time"] = elapsed
            
            # Lưu từng trang vào Database (Tránh 16MB)
            save_document_pages(job_id, result["pages"])
            
            # Cập nhật hoàn tất
            update_document_status(job_id, status="completed", stats=stats_data)
            logger.info(f"Job [{job_id}] hoàn tất thành công trong {elapsed}s!")
            
    except Exception as ex:
        logger.error(f"Job [{job_id}] thất bại: {str(ex)}")
        update_document_status(job_id, status="failed", error_message=str(ex))
    finally:
        # Dọn dẹp file PDF tạm để rỗng ổ cứng
        if Path(upload_path).exists():
            Path(upload_path).unlink()


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

    # 1. Tạo bản ghi ban đầu trong DB (Lấy Job ID)
    title = Path(file.filename).stem.replace("_", " ")
    job_id = create_document_record(filename=file.filename, title=title)

    # 2. Lưu file xuống đĩa (Streaming)
    safe_filename = f"{job_id}_{file.filename}"
    upload_path = _UPLOAD_DIR / safe_filename
    output_path = _OUTPUT_DIR / f"{job_id}_result.md"

    try:
        with upload_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        update_document_status(job_id, status="failed", error_message="Lỗi lưu file vật lý")
        raise HTTPException(status_code=500, detail="Lỗi lưu file xuống đĩa")
    finally:
        file.file.close()

    # 3. Kích hoạt Background Task
    background_tasks.add_task(
        process_ocr_background,
        job_id=job_id,
        upload_path=str(upload_path),
        output_path=str(output_path),
        document_title=title
    )

    return {
        "message": "File đã được tiếp nhận và đang xử lý ngầm.",
        "job_id": job_id,
        "status": "queued"
    }


# -------------------------------------------------------------
# API: Truy vấn trạng thái (Dành cho Frontend hỏi thăm tiến độ)
# -------------------------------------------------------------
@router.get("/status/{job_id}", summary="Kiểm tra trạng thái tiến trình OCR")
async def check_job_status(job_id: str):
    doc = get_document_status(job_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Không tìm thấy Job ID này trong hệ thống")
    return doc