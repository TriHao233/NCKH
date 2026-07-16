from firebase_admin import auth


def verify_firebase_token(id_token: str) -> dict:
    """Xác thực Firebase ID token và trả về decoded token. Raise nếu không hợp lệ/hết hạn."""
    return auth.verify_id_token(id_token)
