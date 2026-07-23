from fastapi import APIRouter, HTTPException
from firebase_admin import auth
from pydantic import BaseModel

from modules.users.service import get_user_service

router = APIRouter()


class TokenRequest(BaseModel):
    id_token: str


@router.post("/login")
def login_user(request: TokenRequest):
    """Verify Firebase identity and synchronize the MongoDB application profile."""
    try:
        claims = auth.verify_id_token(request.id_token)
        user = get_user_service().sync_from_claims(claims)
        if not user["is_active"]:
            raise HTTPException(status_code=403, detail="Tài khoản đã bị khóa")
        return {"message": "Đăng nhập thành công", "user": user}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=401,
            detail="Firebase ID token không hợp lệ hoặc đã hết hạn",
        ) from exc
