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
        
        # NẾU LÀ ĐĂNG NHẬP GOOGLE LẦN ĐẦU (Chưa có trong MongoDB)
        if not user_info:
            email = decoded_token.get('email', '')
            name = decoded_token.get('name', 'Người dùng Google')
            picture = decoded_token.get('picture', '') # Avatar từ Google

            user_info = {
                "uid": uid,
                "Full name": name,
                "Email": email,
                "Địa Chỉ": "",  
                "School": "",          
                "role": "Giảng viên",
                "avatar": picture, # Lưu thêm avatar
                "created_at": datetime.utcnow(),
                "status": "active"
            }
            # Lưu vào MongoDB
            users_collection.insert_one(user_info)
            # Xóa _id sau khi insert để trả về JSON không bị lỗi
            if "_id" in user_info:
                del user_info["_id"]

        return {
            "message": "Đăng nhập thành công",
            "user": user_info
        }
    
    except Exception as e:
        raise HTTPException(status_code=401, detail="Token không hợp lệ hoặc đã hết hạn")