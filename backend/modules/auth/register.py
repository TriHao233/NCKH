from fastapi import APIRouter, HTTPException, status
from firebase_admin import auth

from modules.users.schemas import PublicRegisterRequest, UserResponse
from modules.users.service import get_user_service

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(payload: PublicRegisterRequest):
    """Public Firebase registration; application role is always Teacher."""
    try:
        return get_user_service().register_teacher(payload)
    except auth.EmailAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail="Email này đã được sử dụng") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Không thể đăng ký tài khoản") from exc
