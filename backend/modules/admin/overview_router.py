from typing import Literal

from fastapi import APIRouter, Depends, Query

from core.config import settings
from core.database import get_database
from core.dependencies import CurrentUser, require_permissions
from modules.admin.overview_service import AdminOverviewService

router = APIRouter(prefix=f"{settings.api_prefix}/admin/overview", tags=["Admin overview"])


def get_admin_overview_service() -> AdminOverviewService:
    return AdminOverviewService(get_database())


@router.get("")
def get_admin_overview(
    _admin: CurrentUser = Depends(require_permissions("admin.overview")),
    service: AdminOverviewService = Depends(get_admin_overview_service),
):
    return service.overview()


@router.get("/documents")
def list_admin_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Literal["UPLOADED", "PROCESSING", "READY", "FAILED"] | None = None,
    search: str | None = Query(None, max_length=200),
    subject_id: str | None = Query(None, pattern="^[0-9a-fA-F]{24}$"),
    owner_id: str | None = Query(None, pattern="^[0-9a-fA-F]{24}$"),
    _admin: CurrentUser = Depends(require_permissions("admin.overview")),
    service: AdminOverviewService = Depends(get_admin_overview_service),
):
    return service.list_documents(page, page_size, status, search, subject_id, owner_id)
