from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
import uvicorn

from app.core.config import get_settings
from app.api.v1.ocr import router as ocr_router
from app.api.v1.chunking import router as chunking_router
from app.api.v1.generate import router as generate_router

settings = get_settings()

app = FastAPI(
    title=f"{settings.app_name}",
    version=settings.app_version,
    description="Ngân hàng câu hỏi RAG API",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ocr_router) 
app.include_router(chunking_router)
app.include_router(generate_router)

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "message": "Hệ thống đang hoạt động!"}

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")

if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=True)