from fastapi import APIRouter, HTTPException, status
from firebase_admin import auth
from datetime import datetime
from database import users_collection
from models import UserRegister

router = APIRouter()

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(user: UserRegister):
    try:
        # 1. Tạo tài khoản trên Firebase
        user_record = auth.create_user(
            email=user.email,
            password=user.password,
            display_name=user.full_name
        )

        # 2. Khởi tạo dữ liệu người dùng trong MongoDB (UserInfo)
        user_data = {
            "uid": user_record.uid,
            "Full name": user.full_name,
            "Email": user.email,
            "Địa Chỉ": "",         # Cột rỗng chờ cập nhật sau
            "School": "",          # Cột rỗng chờ cập nhật sau
            "role": "Giảng viên",
            "created_at": datetime.utcnow(),
            "status": "active"
        }
        users_collection.insert_one(user_data)

        return {"message": "Đăng ký thành công!", "uid": user_record.uid}

    except auth.EmailAlreadyExistsError:
        raise HTTPException(status_code=400, detail="Email này đã được sử dụng.")
    except Exception as e:
        if 'user_record' in locals():
            auth.delete_user(user_record.uid) # Rollback trên Firebase nếu MongoDB lỗi
        raise HTTPException(status_code=500, detail=str(e))