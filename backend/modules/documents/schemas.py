from enum import Enum
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DocumentStatus(str, Enum):
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


class DocumentCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    original_filename: str = Field(..., min_length=1, max_length=300)
    subject_id: str | None = None
    chapter_id: str | None = None
    original_uri: str | None = None
    size_bytes: int | None = Field(None, ge=0)
    sha256: str | None = None


class DocumentUpdateRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    subject_id: str | None = None
    chapter_id: str | None = None


class DocumentSharingRequest(BaseModel):
    owner_user_id: str | None = None
    shared_with_user_ids: list[str] = Field(default_factory=list, max_length=100)
    shared_scope: str = Field("PRIVATE", pattern="^(PRIVATE|SUBJECT)$")


class DocumentResponse(BaseModel):
    id: str
    title: str
    original_filename: str
    status: DocumentStatus
    subject_id: str | None
    chapter_id: str | None
    uploaded_by_user_id: str | None
    shared_with_user_ids: list[str] = Field(default_factory=list)
    shared_scope: str = "PRIVATE"
    current_version: int
    page_count: int | None
    artifacts: list[dict[str, Any]]
    current_processing: dict[str, Any]
    pipeline_summary: dict[str, Any]
    latest_error: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class DocumentJobResponse(BaseModel):
    id: str
    document_id: str
    document_version: int | None = None
    job_type: str
    attempt_no: int | None = None
    status: str
    progress: int | None = None
    stats: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    can_retry: bool = False
    can_cancel: bool = False
    queued_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    worker_id: str | None = None
    heartbeat_at: datetime | None = None
    lease_expires_at: datetime | None = None
    checkpoint: dict[str, Any] | None = None


class DocumentJobListResponse(BaseModel):
    items: list[DocumentJobResponse]


class DocumentJobActionResponse(BaseModel):
    job: DocumentJobResponse


class DocumentPageResponse(BaseModel):
    id: str
    document_id: str
    document_version: int | None = None
    ocr_job_id: str | None = None
    processing_revision_id: str | None = None
    revision_no: int | None = None
    page_number: int
    raw_text: str | None = None
    cleaned_text: str | None = None
    formula_blocks: list[Any] = Field(default_factory=list)
    layout_blocks: list[Any] = Field(default_factory=list)
    visual_blocks: list[Any] = Field(default_factory=list)
    extraction_method: str | None = None
    quality_flags: list[str] = Field(default_factory=list)
    corrected_from_page_id: str | None = None
    corrected_by_user_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DocumentPageListResponse(BaseModel):
    items: list[DocumentPageResponse]


class DocumentPageUpdateRequest(BaseModel):
    cleaned_text: str = Field(..., max_length=500_000)


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int
