import logging
from dataclasses import dataclass
from typing import Callable

from bson import ObjectId
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth

from core.database import get_rag_db
from modules.auth.session_repository import get_firebase_session_repository

bearer_scheme = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)

# Keep in sync with modules/auth/login.py's TOKEN_CLOCK_SKEW_SECONDS.
TOKEN_CLOCK_SKEW_SECONDS = 10


@dataclass(frozen=True)
class CurrentUser:
    id: ObjectId
    firebase_uid: str
    email: str
    role: str
    is_active: bool


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Thiếu Firebase ID token",
        )
    try:
        claims = auth.verify_id_token(
            credentials.credentials,
            clock_skew_seconds=TOKEN_CLOCK_SKEW_SECONDS,
        )
    except Exception as exc:
        logger.warning("Firebase ID token verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firebase ID token không hợp lệ hoặc đã hết hạn",
        ) from exc

    user = get_rag_db().users.find_one({"firebase_uid": claims["uid"]})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản chưa được đồng bộ với hệ thống",
        )
    if not user.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tài khoản đã bị khóa")
    get_firebase_session_repository().upsert(
        claims["uid"],
        credentials.credentials,
    )
    return CurrentUser(
        id=user["_id"],
        firebase_uid=user["firebase_uid"],
        email=user.get("email", ""),
        role=user["role"],
        is_active=user.get("is_active", True),
    )


def require_roles(*roles: str) -> Callable:
    allowed = set(roles)

    def dependency(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Yêu cầu role: {', '.join(sorted(allowed))}",
            )
        return current_user

    return dependency


require_admin = require_roles("Admin")
require_teacher_or_admin = require_roles("Admin", "Teacher")
require_reviewer_or_admin = require_roles("Admin", "Reviewer")
require_teacher_reviewer_or_admin = require_roles("Admin", "Teacher", "Reviewer")
