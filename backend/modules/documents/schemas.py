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


class DocumentResponse(BaseModel):
    id: str
    title: str
    original_filename: str
    status: DocumentStatus
    subject_id: str | None
    chapter_id: str | None
    uploaded_by_user_id: str | None
    current_version: int
    page_count: int | None
    artifacts: list[dict[str, Any]]
    current_processing: dict[str, Any]
    pipeline_summary: dict[str, Any]
    latest_error: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int
