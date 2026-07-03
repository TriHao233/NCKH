# backend/auth/login.py
from fastapi import APIRouter, HTTPException, status
from firebase_admin import auth
from models import TokenRequest
from database import users_collection
from datetime import datetime # Thêm import này

router = APIRouter()

@router.post("/login")
async def login_user(request: TokenRequest):
    try:
        # Xác thực Token từ Frontend gửi xuống
        decoded_token = auth.verify_id_token(request.id_token)
        uid = decoded_token['uid']
        
        # Lấy thêm thông tin từ MongoDB
        user_info = users_collection.find_one({"uid": uid}, {"_id": 0})

        # 'picture' chỉ xuất hiện trong token khi đăng nhập bằng Google
        google_picture = decoded_token.get('picture', '')

        # NẾU LÀ ĐĂNG NHẬP GOOGLE LẦN ĐẦU (Chưa có trong MongoDB)
        if not user_info:
            email = decoded_token.get('email', '')
            name = decoded_token.get('name', 'Người dùng Google')

            user_info = {
                "uid": uid,
                "Full name": name,
                "Email": email,
                "Địa Chỉ": "",
                "School": "",
                "role": "Giảng viên",
                "avatar": google_picture, # Lưu ảnh đại diện lấy từ tài khoản Google
                "created_at": datetime.utcnow(),
                "status": "active"
            }
            # Lưu vào MongoDB
            users_collection.insert_one(user_info)
            # Xóa _id sau khi insert để trả về JSON không bị lỗi
            if "_id" in user_info:
                del user_info["_id"]

        # Tài khoản đã tồn tại: đồng bộ lại ảnh đại diện Google mỗi lần đăng nhập
        # (phòng trường hợp user đổi ảnh trên Google, hoặc tài khoản cũ chưa từng có avatar)
        elif google_picture and user_info.get("avatar") != google_picture:
            users_collection.update_one({"uid": uid}, {"$set": {"avatar": google_picture}})
            user_info["avatar"] = google_picture

        return {
            "message": "Đăng nhập thành công",
            "user": user_info
        }
    
    except Exception as e:
        raise HTTPException(status_code=401, detail="Token không hợp lệ hoặc đã hết hạn")