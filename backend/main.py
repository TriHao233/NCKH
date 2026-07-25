import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import RedirectResponse

from core.bootstrap import bootstrap_database
from core.config import settings
from core.database import close_database, ping_database
from core.dependencies import require_teacher_or_admin
from core.firebase import init_firebase
from core.logging import setup_logging
from modules.auth import login, profile, register
from modules.catalog.router import router as catalog_router
from modules.documents.router import router as documents_router
from modules.generation.generate import router as generation_router
from modules.ocr.ocr import router as ocr_router
from modules.questions.router import router as questions_router
from modules.questions.workflow_router import router as question_workflow_router
from modules.rag.chunking import router as rag_router
from modules.users.router import router as users_router

setup_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_firebase()
    await asyncio.to_thread(ping_database)
    await asyncio.to_thread(bootstrap_database)
    try:
        yield
    finally:
        close_database()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)
if settings.allowed_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

auth_prefix = f"{settings.api_prefix}/auth"
app.include_router(register.router, prefix=auth_prefix, tags=["Authentication"])
app.include_router(login.router, prefix=auth_prefix, tags=["Authentication"])
app.include_router(profile.router, prefix=auth_prefix, tags=["Authentication"])
app.include_router(users_router)
app.include_router(catalog_router)
app.include_router(documents_router)
app.include_router(questions_router)
app.include_router(question_workflow_router)

firebase_guard = [Depends(require_teacher_or_admin)]
app.include_router(ocr_router, dependencies=firebase_guard)
app.include_router(rag_router, dependencies=firebase_guard)
app.include_router(generation_router, dependencies=firebase_guard)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "message": "Hệ thống đang hoạt động!"}


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")
