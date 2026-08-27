from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from core.config import settings


class EvaluationScores(BaseModel):
    faithfulness: float = Field(..., ge=0, le=1)
    contextual_relevancy: float = Field(..., ge=0, le=1)
    answer_relevancy: float = Field(..., ge=0, le=1)
    bloom_alignment: float = Field(..., ge=0, le=1)
    clo_alignment: float = Field(..., ge=0, le=1)


class EvaluationCreateRequest(BaseModel):
    expected_version: int = Field(..., ge=1)
    scores: EvaluationScores
    feedback: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    evaluator_model_code: str = "manual-or-external-evaluator"
    model_snapshot: dict[str, Any] = Field(default_factory=dict)
    model_execution: dict[str, Any] = Field(default_factory=dict)
    raw_model_response: str | None = None
    policy_snapshot: dict[str, Any] = Field(default_factory=dict)
    prompt_snapshot: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int | None = Field(None, ge=0)
    evaluation_job_id: str | None = None
    trigger: str | None = None


class ReviewOverride(BaseModel):
    applied: bool = False
    score: float | None = Field(None, ge=0, le=1)
    color: Literal["RED", "YELLOW", "GREEN"] | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def require_reason(self):
        if self.applied and not (self.reason or "").strip():
            raise ValueError("Lý do ghi đè (override reason) là bắt buộc")
        return self


class ReviewRubricItem(BaseModel):
    key: str = Field(..., min_length=1, max_length=80)
    label: str = Field(..., min_length=1, max_length=160)
    passed: bool
    note: str = Field("", max_length=500)


class ReviewCriterionAssessment(BaseModel):
    key: Literal[
        "faithfulness",
        "contextual_relevancy",
        "answer_relevancy",
        "bloom_alignment",
        "clo_alignment",
    ]
    label: str = Field(..., min_length=1, max_length=160)
    rating: Literal["PASS", "REVIEW", "FAIL", "NO_DATA"]
    note: str = Field("", max_length=1000)
    source_chunk_id: str | None = Field(None, max_length=120)
    page_number: int | None = Field(None, ge=1)


class ReviewRevisionIssue(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    severity: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"
    detail: str = Field("", max_length=1000)
    source_chunk_id: str | None = Field(None, max_length=120)
    page_number: int | None = Field(None, ge=1)


class StructuredReviewForm(BaseModel):
    checklist: list[ReviewRubricItem] = Field(default_factory=list, max_length=12)
    criterion_assessments: list[ReviewCriterionAssessment] = Field(default_factory=list, max_length=5)
    overall_note: str = Field("", max_length=2000)
    revision_issues: list[ReviewRevisionIssue] = Field(default_factory=list, max_length=20)

    def has_reason(self) -> bool:
        if self.overall_note.strip():
            return True
        return any(
            issue.title.strip() or issue.detail.strip()
            for issue in self.revision_issues
        )


class ReviewDraftUpsertRequest(BaseModel):
    expected_version: int = Field(..., ge=1)
    decision: Literal["APPROVED", "REJECTED", "NEEDS_REVISION"] | None = None
    draft: dict[str, Any] = Field(default_factory=dict)


class AutoEvaluationRequest(BaseModel):
    expected_version: int = Field(..., ge=1)
    evaluator_model_code: str = Field(
        default_factory=lambda: settings.evaluation_model_provider,
        min_length=1,
        max_length=80,
    )
    fallback_to_heuristic: bool = False


class ReviewCreateRequest(BaseModel):
    expected_version: int = Field(..., ge=1)
    decision: Literal["APPROVED", "REJECTED", "NEEDS_REVISION"]
    note: str = Field("", max_length=2000)
    override: ReviewOverride = Field(default_factory=ReviewOverride)
    review_form: StructuredReviewForm = Field(default_factory=StructuredReviewForm)
    secondary_required: bool = False
    secondary_reason: str = Field("", max_length=500)

    @model_validator(mode="after")
    def require_structured_reason(self):
        has_reason = bool(self.note.strip()) or self.review_form.has_reason()
        if self.decision == "REJECTED" and not has_reason:
            raise ValueError("Reject cần ghi rõ lý do")
        if self.decision == "NEEDS_REVISION" and not self.review_form.revision_issues:
            raise ValueError("Cần ít nhất một lỗi cần Teacher sửa")
        return self


class QuestionCommentCreateRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=2000)
    mention_user_ids: list[str] = Field(default_factory=list, max_length=20)


class QuestionCommentUpdateRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=2000)


class SecondaryReviewRequest(BaseModel):
    required: bool = True
    reason: str = Field("", max_length=500)
    reviewer_user_id: str | None = Field(None, min_length=1, max_length=120)


class ReviewAssignmentRequest(BaseModel):
    reviewer_user_id: str | None = Field(None, min_length=1, max_length=120)
    note: str = Field("", max_length=500)


class MoodlePublicationRequest(BaseModel):
    expected_version: int = Field(..., ge=1)
    target_id: str | None = Field(None, min_length=1, max_length=120)
    moodle_site_id: str = Field("demo-moodle", min_length=1, max_length=120)
    course_id: str = Field("ctdl-demo", min_length=1, max_length=120)
    category_id: str = Field("qbank-demo", min_length=1, max_length=120)
    export_format: Literal["GIFT", "XML", "BOTH"] = "BOTH"
    mock: bool = True
