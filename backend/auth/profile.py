# backend/auth/profile.py
from fastapi import APIRouter, HTTPException
from firebase_admin import auth
from pymongo import ReturnDocument
from models import ProfileUpdate
from database import users_collection

router = APIRouter()

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

    result = users_collection.find_one_and_update(
        {"uid": uid},
        {"$set": update_fields},
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0},
    )

    if not result:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")

    return {"message": "Cập nhật hồ sơ thành công", "user": result}
