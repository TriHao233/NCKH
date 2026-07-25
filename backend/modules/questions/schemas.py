from enum import Enum
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class QuestionOrigin(str, Enum):
    AI = "AI"
    MANUAL = "MANUAL"
    IMPORT = "IMPORT"


class QuestionCreateRequest(BaseModel):
    content: str = Field(..., min_length=1)
    question_type: str = Field("trac_nghiem", min_length=1)
    bloom_level: int | None = Field(None, ge=1, le=6)
    question_data: dict[str, Any] = Field(default_factory=dict)
    subject_id: str | None = None
    chapter_id: str | None = None
    document_id: str | None = None
    chunk_id: str | None = None
    source_chunk_ids: list[str] = Field(default_factory=list)
    clo_ids: list[str] = Field(default_factory=list)


class QuestionUpdateRequest(BaseModel):
    expected_version: int = Field(..., ge=1)
    content: str | None = Field(None, min_length=1)
    question_type: str | None = Field(None, min_length=1)
    bloom_level: int | None = Field(None, ge=1, le=6)
    question_data: dict[str, Any] | None = None
    subject_id: str | None = None
    chapter_id: str | None = None
    chunk_id: str | None = None
    source_chunk_ids: list[str] | None = None
    clo_ids: list[str] | None = None
    change_note: str = Field("Question edited", min_length=1, max_length=500)


class QuestionResponse(BaseModel):
    id: str
    question_code: str
    current_version: int
    current_version_id: str
    approved_version_id: str | None
    lifecycle_status: str
    evaluation_status: str
    review_status: str
    publication_status: str
    content: str
    question_data: dict[str, Any]
    classification: dict[str, Any]
    clos: list[Any]
    sources: list[dict[str, Any]]
    content_hash: str
    quality_summary: dict[str, Any]
    latest_review_id: str | None
    created_at: datetime
    updated_at: datetime


class QuestionVersionResponse(BaseModel):
    id: str
    version: int
    origin: QuestionOrigin
    generation_run_id: str | None
    document_id: str | None
    created_by_user_id: str | None
    generated_by_model_id: str | None
    classification: dict[str, Any]
    clos: list[Any]
    content: str
    question_data: dict[str, Any]
    sources: list[dict[str, Any]]
    keywords: list[Any]
    content_hash: str
    change_note: str
    created_at: datetime


class QuestionListResponse(BaseModel):
    items: list[QuestionResponse]
    total: int
    page: int
    page_size: int
