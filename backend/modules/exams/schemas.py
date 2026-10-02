from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

# Keep legacy matrix values readable without changing their original Bloom level.
LEGACY_COGNITIVE_LEVELS = {
    "nhan_biet": "nho",
    "thong_hieu": "hieu",
    "van_dung_cao": "phan_tich",
}


def normalize_cognitive_level(value):
    return LEGACY_COGNITIVE_LEVELS.get(value, value) if isinstance(value, str) else value


COGNITIVE_LEVEL_TO_BLOOM = {
    "nho": 1,
    "hieu": 2,
    "van_dung": 3,
    "phan_tich": 4,
    "danh_gia": 5,
    "sang_tao": 6,
}

MAX_VARIANTS_PER_EXAM = 4


class CognitiveLevel(str, Enum):
    NHO = "nho"
    HIEU = "hieu"
    VAN_DUNG = "van_dung"
    PHAN_TICH = "phan_tich"
    DANH_GIA = "danh_gia"
    SANG_TAO = "sang_tao"

    @classmethod
    def _missing_(cls, value):
        normalized = normalize_cognitive_level(value)
        return cls(normalized) if normalized != value else None


class QuestionDifficulty(str, Enum):
    DE = "de"
    TRUNG_BINH = "trung_binh"
    KHO = "kho"


class ExamStatus(str, Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    FINALIZED = "FINALIZED"
    ARCHIVED = "ARCHIVED"


class ExamHeaderConfig(BaseModel):
    school_name: str = Field("", max_length=300)
    faculty_name: str = Field("", max_length=300)
    exam_name: str = Field("", max_length=300)
    subject_name: str = Field("", max_length=300)
    duration_minutes: int = Field(60, ge=1, le=600)
    class_name: str | None = None
    room: str | None = None
    exam_date: str | None = None


class MatrixCell(BaseModel):
    chapter_id: str | None = None
    cognitive_level: CognitiveLevel
    difficulty: QuestionDifficulty | None = None
    count: int = Field(..., ge=1)


class ExamMatrixRequest(BaseModel):
    cells: list[MatrixCell] = Field(default_factory=list)


class MatrixCellAvailability(BaseModel):
    chapter_id: str | None
    cognitive_level: CognitiveLevel
    difficulty: QuestionDifficulty | None = None
    requested: int
    available: int
    sufficient: bool


class ExamCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=300)
    exam_title: str = Field(..., min_length=1, max_length=300)
    subject_id: str = Field(..., min_length=1)
    question_count: int = Field(..., ge=1, le=200)
    header: ExamHeaderConfig = Field(default_factory=ExamHeaderConfig)

    @field_validator("name", "exam_title")
    @classmethod
    def validate_title(cls, value):
        if not value.strip():
            raise ValueError("Tên đề thi và tên kỳ thi không được để trống")
        return value.strip()


class ExamUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=300)
    exam_title: str | None = Field(None, min_length=1, max_length=300)
    question_count: int | None = Field(None, ge=1, le=200)
    header: ExamHeaderConfig | None = None

    @field_validator("name", "exam_title")
    @classmethod
    def validate_title(cls, value):
        return ExamCreateRequest.validate_title(value) if value is not None else value


class ExamStatusUpdateRequest(BaseModel):
    status: ExamStatus


class AddQuestionsManualRequest(BaseModel):
    question_ids: list[str] = Field(..., min_length=1)


class ExamQuestionRef(BaseModel):
    question_id: str
    version_id: str
    content_snapshot: dict[str, Any]


class ExamResponse(BaseModel):
    id: str
    name: str
    exam_title: str
    subject_id: str
    question_count: int
    header: ExamHeaderConfig
    matrix: list[MatrixCell] = Field(default_factory=list)
    questions: list[ExamQuestionRef] = Field(default_factory=list)
    status: str
    variant_count: int = 0
    delivery_mode: str = "paper"
    time_limit_seconds: int | None = None
    scoring_config: dict[str, Any] | None = None
    lms_export_status: str = "not_exported"
    created_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ExamListResponse(BaseModel):
    items: list[ExamResponse]
    total: int
    page: int
    page_size: int


class ExamQuestionPoolResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int
    page: int
    page_size: int


class ExamVariantCreateRequest(BaseModel):
    exam_code: str = Field(..., min_length=1, max_length=40)
    shuffle: bool = True

    @field_validator("exam_code")
    @classmethod
    def validate_code(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Mã đề không được để trống")
        if any(character in value for character in '\r\n"/\\'):
            raise ValueError("Mã đề chứa ký tự không hợp lệ")
        return value


class ExamVariantQuestionEntry(BaseModel):
    order: int
    question_id: str
    content_snapshot: dict[str, Any]
    option_order: list[int] | None = None


class ExamVariantResponse(BaseModel):
    id: str
    exam_id: str
    exam_code: str
    questions: list[ExamVariantQuestionEntry]
    answer_key: dict[str, Any]
    created_at: datetime


class ExamPreviewQuestion(BaseModel):
    number: int
    content: str
    question_type: str
    options: list[dict[str, Any]]


class ExamPreviewResponse(BaseModel):
    header: ExamHeaderConfig
    exam_code: str
    questions: list[ExamPreviewQuestion]
