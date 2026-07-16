from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from core.config import settings
from core.database import init_firebase
from core.logging import setup_logging
from modules.auth import register, login, profile
from modules.ocr.router import router as ocr_router
from modules.rag.router import router as rag_router
from modules.generation.router import router as generation_router

setup_logging()
init_firebase()

app = FastAPI(title=settings.app_name, version=settings.app_version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(register.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(login.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(profile.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(ocr_router)
app.include_router(rag_router)
app.include_router(generation_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "message": "Hệ thống đang hoạt động!"}


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")
