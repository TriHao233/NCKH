from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status

from core.config import settings
from core.dependencies import CurrentUser, require_teacher_or_admin
from modules.documents.schemas import (
    DocumentCreateRequest,
    DocumentJobListResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentStatus,
    DocumentUpdateRequest,
)
from modules.documents.service import DocumentService, get_document_service
from modules.ocr.ocr import queue_pdf_ocr_upload

router = APIRouter(prefix=f"{settings.api_prefix}/documents", tags=["Documents"])


@router.get("", response_model=DocumentListResponse)
def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    document_status: DocumentStatus | None = Query(None, alias="status"),
    search: str | None = None,
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    service: DocumentService = Depends(get_document_service),
):
    return service.list(
        page,
        page_size,
        document_status.value if document_status else None,
        search,
        current_user,
    )


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def create_document(
    payload: DocumentCreateRequest,
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    service: DocumentService = Depends(get_document_service),
):
    try:
        return service.create(payload, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_document_pdf(
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


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: str,
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    service: DocumentService = Depends(get_document_service),
):
    try:
        document = service.get(document_id, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not document:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    return document


@router.get("/{document_id}/jobs", response_model=DocumentJobListResponse)
def list_document_jobs(
    document_id: str,
    limit: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    service: DocumentService = Depends(get_document_service),
):
    try:
        result = service.list_jobs(document_id, current_user, limit=limit)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    return result


@router.patch("/{document_id}", response_model=DocumentResponse)
def update_document(
    document_id: str,
    payload: DocumentUpdateRequest,
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    service: DocumentService = Depends(get_document_service),
):
    try:
        document = service.update(document_id, payload, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not document:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    service: DocumentService = Depends(get_document_service),
):
    try:
        deleted = service.archive(document_id, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
