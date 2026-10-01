from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ContactCategory(str, Enum):
    REVIEW_REQUEST = "REVIEW_REQUEST"
    BUG = "BUG"
    SUPPORT = "SUPPORT"
    FEEDBACK = "FEEDBACK"
    CONTENT_ISSUE = "CONTENT_ISSUE"


class ContactStatus(str, Enum):
    NEW = "NEW"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    WITHDRAWN = "WITHDRAWN"


class ContactRequestCreate(BaseModel):
    category: ContactCategory
    title: str = Field(..., min_length=1, max_length=300)
    content: str = Field(..., min_length=1, max_length=1000)


class ContactRequestUpdate(BaseModel):
    category: ContactCategory | None = None
    title: str | None = Field(None, min_length=1, max_length=300)
    content: str | None = Field(None, min_length=1, max_length=1000)


class ContactMessageCreate(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)


class ContactStatusUpdate(BaseModel):
    status: ContactStatus


class ContactResponseSubmit(BaseModel):
    status: ContactStatus | None = None
    message: str | None = Field(None, max_length=5000)


class ContactMessageResponse(BaseModel):
    id: str
    request_id: str
    sender_id: str
    sender_name: str = ""
    sender_role: str = ""
    message: str
    created_at: datetime


class ContactRequestEventResponse(BaseModel):
    id: str
    actor_name: str = ""
    action: str
    old_value: dict = Field(default_factory=dict)
    new_value: dict = Field(default_factory=dict)
    created_at: datetime


class ContactRequestResponse(BaseModel):
    id: str
    ticket_code: str
    user_id: str
    user_name: str = ""
    user_email: str = ""
    category: ContactCategory
    title: str
    content: str
    status: ContactStatus
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None
    withdrawn_at: datetime | None = None
    deleted_at: datetime | None = None
    deleted_by: str | None = None
    message_count: int = 0


class ContactRequestDetail(ContactRequestResponse):
    messages: list[ContactMessageResponse] = Field(default_factory=list)
    events: list[ContactRequestEventResponse] = Field(default_factory=list)


class ContactRequestListResponse(BaseModel):
    items: list[ContactRequestResponse]
    total: int
    page: int
    page_size: int
