from fastapi import APIRouter, Depends, HTTPException, Response, status
from firebase_admin import auth
from pydantic import BaseModel

from core.dependencies import CurrentUser, get_current_user
from modules.auth.session_repository import get_firebase_session_repository
from modules.users.service import get_user_service

router = APIRouter()


class TokenRequest(BaseModel):
    id_token: str


@router.post("/login")
def login_user(request: TokenRequest):
    """Verify Firebase identity and synchronize the MongoDB application profile."""
    try:
        claims = auth.verify_id_token(request.id_token)
    except Exception as exc:
        raise HTTPException(
            status_code=401,
            detail="Firebase ID token không hợp lệ hoặc đã hết hạn",
        ) from exc

    try:
        user = get_user_service().sync_from_claims(claims)
        if not user["is_active"]:
            raise HTTPException(status_code=403, detail="Tài khoản đã bị khóa")
        get_firebase_session_repository().upsert(claims["uid"], request.id_token)
        return {"message": "Đăng nhập thành công", "user": user}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Không thể đồng bộ phiên đăng nhập",
        ) from exc


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_user(
    current_user: CurrentUser = Depends(get_current_user),
) -> Response:
    get_firebase_session_repository().upsert(current_user.firebase_uid, None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
