from fastapi import APIRouter, Depends, HTTPException, Query, status

from core.config import settings
from core.dependencies import CurrentUser, require_teacher_or_admin
from modules.documents.schemas import (
    DocumentCreateRequest,
    DocumentListResponse,
    DocumentResponse,
    DocumentStatus,
    DocumentUpdateRequest,
)
from modules.documents.service import DocumentService, get_document_service

router = APIRouter(prefix=f"{settings.api_prefix}/documents", tags=["Documents"])


@router.get("", response_model=DocumentListResponse)
def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    document_status: DocumentStatus | None = Query(None, alias="status"),
    search: str | None = None,
    _user: CurrentUser = Depends(require_teacher_or_admin),
    service: DocumentService = Depends(get_document_service),
):
    return service.list(
        page,
        page_size,
        document_status.value if document_status else None,
        search,
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


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: str,
    _user: CurrentUser = Depends(require_teacher_or_admin),
    service: DocumentService = Depends(get_document_service),
):
    try:
        document = service.get(document_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not document:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    return document


@router.patch("/{document_id}", response_model=DocumentResponse)
def update_document(
    document_id: str,
    payload: DocumentUpdateRequest,
    _user: CurrentUser = Depends(require_teacher_or_admin),
    service: DocumentService = Depends(get_document_service),
):
    try:
        document = service.update(document_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not document:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    _user: CurrentUser = Depends(require_teacher_or_admin),
    service: DocumentService = Depends(get_document_service),
):
    try:
        deleted = service.archive(document_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
