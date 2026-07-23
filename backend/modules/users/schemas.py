from enum import Enum
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class RoleEnum(str, Enum):
    ADMIN = "Admin"
    TEACHER = "Teacher"


class UserProfile(BaseModel):
    school: str = ""
    address: str = ""
    avatar: str = ""


class UserCreateRequest(BaseModel):
    email: str = Field(
        ...,
        min_length=3,
        max_length=320,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    password: str = Field(..., min_length=6, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=120)
    role: RoleEnum = RoleEnum.TEACHER
    profile: UserProfile = Field(default_factory=UserProfile)


class PublicRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(
        ...,
        min_length=3,
        max_length=320,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    password: str = Field(..., min_length=6, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=120)


class UserSelfUpdateRequest(BaseModel):
    display_name: Optional[str] = Field(None, min_length=1, max_length=120)
    profile: Optional[UserProfile] = None


class UserAdminUpdateRequest(UserSelfUpdateRequest):
    role: Optional[RoleEnum] = None
    is_active: Optional[bool] = None


class UserResponse(BaseModel):
    id: str
    firebase_uid: str
    email: str
    display_name: str
    role: RoleEnum
    profile: UserProfile
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
    page: int
    page_size: int
