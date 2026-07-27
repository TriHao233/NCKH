from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class MoodleTargetPayload(BaseModel):
    site_key: str = Field(..., min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    site_name: str = Field(..., min_length=1, max_length=160)
    mode: Literal["MOCK", "REST_API"] = "MOCK"
    base_url: str = Field("", max_length=500)
    token_env_var: str = Field("", max_length=120)
    default_course_id: str = Field(..., min_length=1, max_length=120)
    default_category_id: str = Field(..., min_length=1, max_length=120)
    allowed_roles: list[Literal["Admin", "Reviewer"]] = Field(
        default_factory=lambda: ["Admin", "Reviewer"],
        min_length=1,
    )
    is_active: bool = True

    @field_validator("site_key", "site_name", "base_url", "token_env_var", "default_course_id", "default_category_id")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        return value.rstrip("/")

    @model_validator(mode="after")
    def validate_runtime_config(self):
        if self.mode == "REST_API":
            if not self.base_url:
                raise ValueError("REST_API target cần base_url")
            if not self.token_env_var:
                raise ValueError("REST_API target cần token_env_var")
        return self
