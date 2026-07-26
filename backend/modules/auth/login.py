import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from firebase_admin import auth
from pydantic import BaseModel
from pymongo import ReturnDocument

from core.bootstrap import SCHEMA_VERSION
from core.database import get_rag_db
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


class DemoLoginRequest(BaseModel):
    username: str
    password: str


DEMO_USERS = {
    "admin": {
        "password": "admin",
        "email": "admin@qbankctu.edu.vn",
        "display_name": "Admin Demo",
        "role": "Admin",
    },
    "reviewer": {
        "password": "reviewer",
        "email": "reviewer@qbankctu.edu.vn",
        "display_name": "Reviewer Demo",
        "role": "Reviewer",
    },
}


def _ensure_demo_firebase_user(email: str, display_name: str):
    try:
        firebase_user = auth.get_user_by_email(email)
        return auth.update_user(
            firebase_user.uid,
            display_name=display_name,
            disabled=False,
            email_verified=True,
        )
    except auth.UserNotFoundError:
        return auth.create_user(
            email=email,
            display_name=display_name,
            disabled=False,
            email_verified=True,
        )


def _ensure_demo_app_user(firebase_uid: str, demo_user: dict) -> dict:
    now = datetime.now(timezone.utc)
    return get_rag_db().users.find_one_and_update(
        {"firebase_uid": firebase_uid},
        {
            "$set": {
                "schema_version": SCHEMA_VERSION,
                "firebase_uid": firebase_uid,
                "email": demo_user["email"].lower(),
                "display_name": demo_user["display_name"],
                "role": demo_user["role"],
                "profile": {"school": "", "address": "", "avatar": ""},
                "is_active": True,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )


@router.post("/demo-login")
def demo_login(request: DemoLoginRequest):
    username = request.username.strip().lower()
    demo_user = DEMO_USERS.get(username)
    if not demo_user or request.password != demo_user["password"]:
        raise HTTPException(status_code=401, detail="Tài khoản demo không chính xác")
    firebase_user = _ensure_demo_firebase_user(
        demo_user["email"],
        demo_user["display_name"],
    )
    app_user = _ensure_demo_app_user(firebase_user.uid, demo_user)
    if not app_user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Tài khoản đã bị khóa")
    custom_token = auth.create_custom_token(firebase_user.uid).decode("utf-8")
    return {"custom_token": custom_token}


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
