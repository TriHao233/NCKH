import asyncio
import hashlib
import logging
import os
import shutil
import time
from pathlib import Path

from docx import Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from core.config import resolve_path, settings
from core.access_policy import has_subject_access
from core.database import get_database
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

DOCX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
SUPPORTED_UPLOAD_TYPES = {
    ".pdf": {
        "artifact_type": "ORIGINAL_PDF",
        "mime_type": "application/pdf",
        "source_format": "pdf",
    },
    ".docx": {
        "artifact_type": "ORIGINAL_DOCX",
        "mime_type": DOCX_MIME_TYPE,
        "source_format": "docx",
    },
}
DOCX_PAGE_CHAR_LIMIT = 12_000


def _ocr_job_cancelled(job_id: str) -> bool:
    status = get_document_status(job_id)
    return ((status or {}).get("job") or {}).get("status") == "CANCELLED"


async def process_ocr_background(
    document_id: str,
    job_id: str,
    upload_path: str,
    output_path: str,
    document_title: str,
):
    try:
        async with gpu_semaphore:
            if _ocr_job_cancelled(job_id):
                return
            update_document_status(document_id, job_id, status="processing")
            started_at = time.time()
            result = await run_in_threadpool(
                run_ocr_pipeline,
                pdf_path=upload_path,
                output_path=output_path,
                document_title=document_title,
            )
            if _ocr_job_cancelled(job_id):
                return
            stats = result["stats"]
            stats["processing_time"] = round(time.time() - started_at, 1)
            save_document_pages(document_id, job_id, result["pages"])
            if _ocr_job_cancelled(job_id):
                return
            update_document_status(document_id, job_id, status="completed", stats=stats)
    except Exception as exc:
        logger.exception("OCR job %s failed", job_id)
        if _ocr_job_cancelled(job_id):
            return
        update_document_status(
            document_id,
            job_id,
            status="failed",
            error_message=str(exc),
        )


def _iter_docx_blocks(document: Document):
    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


def _table_to_markdown(table: Table) -> str:
    rows = []
    for row in table.rows:
        cells = [" ".join(cell.text.split()) for cell in row.cells]
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def extract_docx_pages(docx_path: str | Path, *, page_char_limit: int = DOCX_PAGE_CHAR_LIMIT) -> tuple[list[dict], dict]:
    document = Document(str(docx_path))
    blocks: list[str] = []
    paragraph_count = 0
    table_count = 0

    for block in _iter_docx_blocks(document):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if text:
                blocks.append(text)
                paragraph_count += 1
        elif isinstance(block, Table):
            text = _table_to_markdown(block).strip()
            if text:
                blocks.append(text)
                table_count += 1

    if not blocks:
        raise ValueError("DOCX không có nội dung văn bản để xử lý")

    pages: list[dict] = []
    current: list[str] = []
    current_length = 0
    for block in blocks:
        block_length = len(block)
        if current and current_length + block_length + 2 > page_char_limit:
            text = "\n\n".join(current).strip()
            pages.append({"page_number": len(pages) + 1, "text": text, "original_text": text, "formula_blocks": []})
            current = []
            current_length = 0
        current.append(block)
        current_length += block_length + 2

    if current:
        text = "\n\n".join(current).strip()
        pages.append({"page_number": len(pages) + 1, "text": text, "original_text": text, "formula_blocks": []})

    stats = {
        "source_format": "docx",
        "page_count": len(pages),
        "paragraph_count": paragraph_count,
        "table_count": table_count,
        "char_count": sum(len(page["text"]) for page in pages),
    }
    return pages, stats


async def process_docx_background(
    document_id: str,
    job_id: str,
    upload_path: str,
    output_path: str,
    document_title: str,
):
    try:
        if _ocr_job_cancelled(job_id):
            return
        update_document_status(document_id, job_id, status="processing")
        started_at = time.time()
        pages, stats = await run_in_threadpool(extract_docx_pages, upload_path)
        if _ocr_job_cancelled(job_id):
            return
        output = Path(output_path)
        output.write_text(
            f"# {document_title}\n\n" + "\n\n---\n\n".join(page["text"] for page in pages),
            encoding="utf-8",
        )
        save_document_pages(document_id, job_id, pages)
        if _ocr_job_cancelled(job_id):
            return
        stats["processing_time"] = round(time.time() - started_at, 1)
        update_document_status(document_id, job_id, status="completed", stats=stats)
    except Exception as exc:
        logger.exception("DOCX extraction job %s failed", job_id)
        if _ocr_job_cancelled(job_id):
            return
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
    safe_filename = Path(file.filename or "").name
    extension = Path(safe_filename).suffix.lower()
    upload_type = SUPPORTED_UPLOAD_TYPES.get(extension)
    if not safe_filename or not upload_type:
        raise HTTPException(status_code=400, detail="Chỉ chấp nhận file PDF hoặc DOCX")

    file.file.seek(0, os.SEEK_END)
    file_size = file.file.tell()
    file.file.seek(0)
    if file_size > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Dung lượng tối đa 50 MB")

    access_database = get_database()
    if (
        subject_id
        and current_user.role != "Admin"
        and getattr(access_database, "subject_memberships", None) is not None
        and not has_subject_access(access_database, current_user.id, subject_id)
    ):
        raise HTTPException(status_code=403, detail="Bạn chưa được phân công vào học phần đã chọn")

    title = Path(safe_filename).stem.replace("_", " ")
    document_id = create_document_record(
        filename=safe_filename,
        title=title,
        uploaded_by_user_id=current_user.id,
        subject_id=subject_id,
        chapter_id=chapter_id,
    )
    job_id = create_ocr_job(document_id, config={"source_format": upload_type["source_format"]})
    upload_path = _UPLOAD_DIR / f"{document_id}_{safe_filename}"
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
            artifact_type=upload_type["artifact_type"],
            mime_type=upload_type["mime_type"],
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

    processor = process_docx_background if upload_type["source_format"] == "docx" else process_ocr_background
    background_tasks.add_task(
        processor,
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
