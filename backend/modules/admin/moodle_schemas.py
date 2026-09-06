from typing import Any, Literal

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
    moodle_version: str = Field("", max_length=80)
    capabilities: dict[str, bool] = Field(default_factory=dict)
    allowed_course_ids: list[str] = Field(default_factory=list, max_length=500)

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


class MoodleIdentityItem(BaseModel):
    external_user_id: str = Field(..., min_length=1, max_length=160)
    username: str = Field("", max_length=160)
    email: str = Field("", max_length=320)
    display_name: str = Field("", max_length=240)
    internal_user_id: str | None = None
    link_token: str | None = None
    is_active: bool = True


class MoodleMembershipItem(BaseModel):
    external_user_id: str = Field(..., min_length=1, max_length=160)
    external_course_id: str = Field(..., min_length=1, max_length=160)
    subject_id: str = Field(..., min_length=1, max_length=120)
    external_role: str = Field(..., min_length=1, max_length=80)
    is_active: bool = True


class MoodleSyncPageRequest(BaseModel):
    site_key: str = Field(..., min_length=1, max_length=80)
    sync_id: str = Field(..., min_length=1, max_length=160)
    checkpoint: str = Field(..., min_length=1, max_length=500)
    next_checkpoint: str | None = Field(None, max_length=500)
    is_last_page: bool = False
    identities: list[MoodleIdentityItem] = Field(default_factory=list, max_length=1000)
    memberships: list[MoodleMembershipItem] = Field(default_factory=list, max_length=3000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MoodleLinkTokenRequest(BaseModel):
    site_key: str = Field(..., min_length=1, max_length=80)
    external_user_id: str = Field(..., min_length=1, max_length=160)
    internal_user_id: str = Field(..., min_length=1, max_length=120)
    expires_in_minutes: int = Field(15, ge=1, le=1440)
