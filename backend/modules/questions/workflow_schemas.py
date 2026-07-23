from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


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
    raw_model_response: str | None = None


class ReviewOverride(BaseModel):
    applied: bool = False
    score: float | None = Field(None, ge=0, le=1)
    color: Literal["RED", "YELLOW", "GREEN"] | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def require_reason(self):
        if self.applied and not (self.reason or "").strip():
            raise ValueError("Override reason is required")
        return self


class ReviewCreateRequest(BaseModel):
    expected_version: int = Field(..., ge=1)
    decision: Literal["APPROVED", "REJECTED", "NEEDS_REVISION"]
    note: str = ""
    override: ReviewOverride = Field(default_factory=ReviewOverride)
