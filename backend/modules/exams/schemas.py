from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

# Mapping từ 4 mức nhận thức VN sang bloom_level (1-6) đã có sẵn trên câu hỏi.
COGNITIVE_LEVEL_TO_BLOOM = {
    "nhan_biet": {1},
    "thong_hieu": {2},
    "van_dung": {3},
    "van_dung_cao": {4, 5, 6},
}

MAX_VARIANTS_PER_EXAM = 4


class CognitiveLevel(str, Enum):
    NHAN_BIET = "nhan_biet"
    THONG_HIEU = "thong_hieu"
    VAN_DUNG = "van_dung"
    VAN_DUNG_CAO = "van_dung_cao"


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
    cognitive_level: CognitiveLevel | None = None
    bloom_levels: list[int] = Field(default_factory=list)
    clo_ids: list[str] = Field(default_factory=list)
    question_types: list[str] = Field(default_factory=list)
    difficulty: QuestionDifficulty
    count: int = Field(..., ge=1)
    marks_per_question: float = Field(1, gt=0, le=100)

    @model_validator(mode="after")
    def normalize_blueprint(self):
        blooms = set(self.bloom_levels)
        if self.cognitive_level:
            blooms.update(COGNITIVE_LEVEL_TO_BLOOM[self.cognitive_level.value])
        if not blooms:
            raise ValueError("Mỗi ô blueprint cần ít nhất một mức Bloom")
        if any(level < 1 or level > 6 for level in blooms):
            raise ValueError("Bloom phải nằm trong khoảng 1–6")
        self.bloom_levels = sorted(blooms)
        self.clo_ids = list(dict.fromkeys(item for item in self.clo_ids if item))
        self.question_types = list(dict.fromkeys(item.strip().lower() for item in self.question_types if item.strip()))
        return self


class ExamMatrixRequest(BaseModel):
    cells: list[MatrixCell] = Field(default_factory=list)


class MatrixCellAvailability(BaseModel):
    chapter_id: str | None
    cognitive_level: CognitiveLevel | None = None
    difficulty: QuestionDifficulty
    requested: int
    available: int
    sufficient: bool
    bloom_levels: list[int] = Field(default_factory=list)
    clo_ids: list[str] = Field(default_factory=list)
    question_types: list[str] = Field(default_factory=list)
    marks_per_question: float = 1
    shortage: int = 0


class ExamCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=300)
    exam_title: str = Field(..., min_length=1, max_length=300)
    subject_id: str = Field(..., min_length=1)
    question_count: int = Field(..., ge=1, le=200)
    header: ExamHeaderConfig = Field(default_factory=ExamHeaderConfig)


class ExamUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=300)
    exam_title: str | None = Field(None, min_length=1, max_length=300)
    question_count: int | None = Field(None, ge=1, le=200)
    header: ExamHeaderConfig | None = None


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
    blueprint_version: int = 2
    total_marks: float = 0
    selection_seed: str | None = None
    coverage_report: dict[str, Any] | None = None
    eligibility_manifest: dict[str, Any] | None = None
    revision: int = 1
    finalized_at: datetime | None = None
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


class ExamVariantQuestionEntry(BaseModel):
    order: int
    question_id: str
    content_snapshot: dict[str, Any]
    option_order: list[int] | None = None
    answer_mapping: dict[str, str] = Field(default_factory=dict)


class ExamVariantResponse(BaseModel):
    id: str
    exam_id: str
    exam_code: str
    questions: list[ExamVariantQuestionEntry]
    answer_key: dict[str, Any]
    seed: str
    exam_revision: int
    permutation: list[str] = Field(default_factory=list)
    export_manifest: dict[str, Any] = Field(default_factory=dict)
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
    answers: list[dict[str, Any]] = Field(default_factory=list)
    export_manifest: dict[str, Any] | None = None
