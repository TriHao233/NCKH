import asyncio
import logging
import shutil
import time
from pathlib import Path

from fastapi.concurrency import run_in_threadpool

from core.config import resolve_path, settings
from modules.ocr.pipeline import run_ocr_pipeline
from modules.ocr.repository import (
    create_document_record,
    get_document_status,
    save_document_pages,
    update_document_status,
)

logger = logging.getLogger(__name__)

gpu_semaphore = asyncio.Semaphore(1)

UPLOAD_DIR = resolve_path(settings.upload_dir)
OCR_OUTPUT_DIR = resolve_path(settings.ocr_output_dir)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OCR_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


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


def create_upload_job(filename: str, file_obj) -> dict:
    """Tạo bản ghi Job (Job ID) và lưu file PDF xuống đĩa. Trả về thông tin cần thiết để enqueue OCR nền."""
    title = Path(filename).stem.replace("_", " ")
    job_id = create_document_record(filename=filename, title=title)

    safe_filename = f"{job_id}_{filename}"
    upload_path = UPLOAD_DIR / safe_filename
    output_path = OCR_OUTPUT_DIR / f"{job_id}_result.md"

    try:
        with upload_path.open("wb") as buffer:
            shutil.copyfileobj(file_obj, buffer)
    except Exception:
        update_document_status(job_id, status="failed", error_message="Lỗi lưu file vật lý")
        raise

    return {
        "job_id": job_id,
        "title": title,
        "upload_path": str(upload_path),
        "output_path": str(output_path),
    }


def get_job_status(job_id: str) -> dict | None:
    return get_document_status(job_id)
