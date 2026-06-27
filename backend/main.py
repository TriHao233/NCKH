from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from auth import register, login 

app = FastAPI(title="QBankCTU API")

# Cấu hình CORS để cho phép Frontend (Vite) gọi API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"], # Cho phép cổng 5173 của React
    allow_credentials=True,
    allow_methods=["*"], # Cho phép tất cả các phương thức (GET, POST, PUT, DELETE)
    allow_headers=["*"], # Cho phép tất cả các header
)

# Gắn các router vào app chính
app.include_router(register.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(login.router, prefix="/api/auth", tags=["Authentication"])

@app.get("/")
def root():
    return {"message": "Server đang chạy thành công!"}