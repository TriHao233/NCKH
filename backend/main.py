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
from core.job_recovery import recover_stale_jobs
from core.logging import setup_logging
from modules.admin.audit_router import router as admin_audit_router
from modules.admin.jobs_router import router as admin_jobs_router
from modules.admin.moodle_router import router as admin_moodle_router
from modules.admin.overview_router import router as admin_overview_router
from modules.auth import login, profile, register
from modules.catalog.router import router as catalog_router
from modules.documents.router import router as documents_router
from modules.exams.router import router as exams_router
from modules.generation.generate import router as generation_router
from modules.notifications.router import router as notifications_router
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
    await asyncio.to_thread(recover_stale_jobs)
    try:
        yield
    finally:
        close_database()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

import time
from fastapi import Request

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000
    
    status = response.status_code
    
    # Add colors to status codes
    if 200 <= status < 300:
        color = "\033[92m" # Green
    elif 300 <= status < 400:
        color = "\033[96m" # Cyan
    elif 400 <= status < 500:
        color = "\033[93m" # Yellow
    else:
        color = "\033[91m" # Red
    reset = "\033[0m"
    
    client_ip = request.client.host if request.client else "unknown"
    
    if request.url.path not in ["/health", "/api/v1/notifications/unread-count"]:
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        method = f"\033[1m{request.method}\033[0m"
        print(f"\033[90m{timestamp}\033[0m | \033[92m  INFO  \033[0m | [{client_ip}] {method:^16} {request.url.path} - {color}{status}{reset} - {process_time:.1f}ms", flush=True)
        
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Idempotency-Key"],
)
if settings.allowed_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

auth_prefix = f"{settings.api_prefix}/auth"
app.include_router(register.router, prefix=auth_prefix, tags=["Authentication"])
app.include_router(login.router, prefix=auth_prefix, tags=["Authentication"])
app.include_router(profile.router, prefix=auth_prefix, tags=["Authentication"])
app.include_router(users_router)
app.include_router(admin_overview_router)
app.include_router(admin_audit_router)
app.include_router(admin_jobs_router)
app.include_router(admin_moodle_router)
app.include_router(catalog_router)
app.include_router(documents_router)
app.include_router(question_workflow_router)
app.include_router(questions_router)
app.include_router(exams_router)
app.include_router(notifications_router)

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
