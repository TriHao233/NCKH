import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status
from firebase_admin import auth
from pydantic import BaseModel

from core.dependencies import CurrentUser, get_current_user
from modules.auth.session_repository import get_firebase_session_repository
from modules.users.service import get_user_service

router = APIRouter()
logger = logging.getLogger(__name__)

# Tolerate small clock drift between this host and Google's servers when
# checking token iat/exp/auth_time, to avoid intermittent 401s on otherwise
# valid tokens.
TOKEN_CLOCK_SKEW_SECONDS = 10


class TokenRequest(BaseModel):
    id_token: str


@router.post("/login")
def login_user(request: TokenRequest):
    """Verify Firebase identity and synchronize the MongoDB application profile."""
    try:
        claims = auth.verify_id_token(
            request.id_token,
            clock_skew_seconds=TOKEN_CLOCK_SKEW_SECONDS,
        )
    except Exception as exc:
        logger.warning("Firebase ID token verification failed on /auth/login: %s", exc)
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
