from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AuditActor(BaseModel):
    type: str | None = None
    user_id: str | None = None
    role: str | None = None
    model_id: str | None = None
    service_name: str | None = None


class AuditEntity(BaseModel):
    type: str | None = None
    id: str | None = None
    version_id: str | None = None


class AuditLogResponse(BaseModel):
    id: str
    action: str
    actor: AuditActor = Field(default_factory=AuditActor)
    entity: AuditEntity = Field(default_factory=AuditEntity)
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)
    changes: list[Any] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    before_hash: str | None = None
    after_hash: str | None = None
    created_at: datetime | None = None


class AuditLogListResponse(BaseModel):
    items: list[AuditLogResponse]
    total: int
    page: int
    page_size: int
