from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.dependencies import CurrentUser, get_current_user
from modules.users.schemas import UserProfile, UserSelfUpdateRequest
from modules.users.service import get_user_service

router = APIRouter()


class ProfileUpdate(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=120)
    school: str = ""
    address: str = ""
    avatar: str = ""


@router.put("/profile")
def update_profile(
    # Deprecated: kept only for backward compatibility with clients that
    # haven't migrated yet. New UI code must use PATCH /users/me instead.
    payload: ProfileUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    user = get_user_service().update_self(
        str(current_user.id),
        UserSelfUpdateRequest(
            display_name=payload.full_name,
            profile=UserProfile(
                school=payload.school,
                address=payload.address,
                avatar=payload.avatar,
            ),
        ),
    )
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    return {"message": "Cập nhật hồ sơ thành công", "user": user}
