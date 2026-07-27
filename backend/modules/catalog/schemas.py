from typing import Any

from pydantic import BaseModel, Field


class ChapterPayload(BaseModel):
    chapter_code: str = Field(..., min_length=1, max_length=40)
    chapter_name: str = Field(..., min_length=1, max_length=200)
    sequence_no: int = Field(1, ge=1)
    is_active: bool = True


class LearningOutcomePayload(BaseModel):
    clo_code: str = Field(..., min_length=1, max_length=40)
    description: str = Field(..., min_length=1, max_length=500)
    target_weight: float = Field(1.0, ge=0, le=1)
    is_active: bool = True


class SubjectPayload(BaseModel):
    subject_code: str = Field(..., min_length=1, max_length=40)
    subject_name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    is_active: bool = True


class SubjectUpdatePayload(BaseModel):
    subject_code: str | None = Field(None, min_length=1, max_length=40)
    subject_name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    is_active: bool | None = None


class ChapterUpdatePayload(BaseModel):
    chapter_code: str | None = Field(None, min_length=1, max_length=40)
    chapter_name: str | None = Field(None, min_length=1, max_length=200)
    sequence_no: int | None = Field(None, ge=1)
    is_active: bool | None = None


class LearningOutcomeUpdatePayload(BaseModel):
    clo_code: str | None = Field(None, min_length=1, max_length=40)
    description: str | None = Field(None, min_length=1, max_length=500)
    target_weight: float | None = Field(None, ge=0, le=1)
    is_active: bool | None = None


class SubjectResponse(BaseModel):
    id: str
    subject_code: str
    subject_name: str
    description: str = ""
    chapters: list[dict[str, Any]] = Field(default_factory=list)
    learning_outcomes: list[dict[str, Any]] = Field(default_factory=list)
    is_active: bool
    usage_counts: dict[str, Any] = Field(default_factory=dict)


class AiModelPayload(BaseModel):
    model_code: str = Field(..., min_length=1, max_length=80)
    model_name: str = Field(..., min_length=1, max_length=160)
    runtime: str = Field("OLLAMA", min_length=1, max_length=80)
    kind: str = Field("CHAT", min_length=1, max_length=80)
    revision: str = "local"
    capabilities: list[str] = Field(default_factory=list)
    priority: int = Field(10, ge=0)
    is_local: bool = True
    is_active: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class AiModelActivationPayload(BaseModel):
    model_code: str = Field(..., min_length=1, max_length=80)
    is_active: bool = True


class AiModelHealthCheckPayload(BaseModel):
    model_code: str = Field(..., min_length=1, max_length=80)
    prompt: str = Field(
        'Return JSON only: {"ok": true}',
        min_length=1,
        max_length=1000,
    )
    timeout_seconds: float = Field(30, ge=1, le=120)


class PromptTemplatePayload(BaseModel):
    template_key: str = Field(..., min_length=1, max_length=120)
    kind: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=160)
    prompt_body: str = Field(..., min_length=1)
    create_new_version: bool = True
    is_active: bool = True


class PromptTemplateActivationPayload(BaseModel):
    template_key: str = Field(..., min_length=1, max_length=120)
    version: int = Field(..., ge=1)
    is_active: bool = True


class PromptTemplateTestPayload(BaseModel):
    context: str = Field(
        "Stack uses LIFO, queue uses FIFO.",
        min_length=1,
        max_length=4000,
    )
    bloom_level: str = Field("hieu", min_length=1, max_length=80)
    question_type: str = Field("trac_nghiem", min_length=1, max_length=80)
    num_questions: int = Field(1, ge=1, le=10)
    instruction: str | None = Field(None, max_length=1000)


class EvaluationPolicyPayload(BaseModel):
    policy_name: str = Field(..., min_length=1, max_length=160)
    weights: dict[str, float]
    thresholds: dict[str, float]
    create_new_version: bool = True
    is_active: bool = True


class EvaluationPolicyActivationPayload(BaseModel):
    policy_name: str = Field(..., min_length=1, max_length=160)
    version: int = Field(..., ge=1)
    is_active: bool = True
