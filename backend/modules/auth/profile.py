from fastapi import APIRouter, HTTPException
from firebase_admin import auth
from pydantic import BaseModel
from pymongo import ReturnDocument

from core.database import get_auth_db

router = APIRouter()


class ProfileUpdate(BaseModel):
    id_token: str
    full_name: str
    school: str = ""
    address: str = ""


@router.put("/profile")
async def update_profile(payload: ProfileUpdate):
    try:
        decoded_token = auth.verify_id_token(payload.id_token)
        uid = decoded_token["uid"]
    except Exception:
        raise HTTPException(status_code=401, detail="Token không hợp lệ hoặc đã hết hạn")

    # Email và uid không được phép chỉnh sửa qua endpoint này
    update_fields = {
        "Full name": payload.full_name,
        "School": payload.school,
        "Địa Chỉ": payload.address,
    }

    result = get_auth_db()["UserInfo"].find_one_and_update(
        {"uid": uid},
        {"$set": update_fields},
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0},
    )

    if not result:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")

    return {"message": "Cập nhật hồ sơ thành công", "user": result}
