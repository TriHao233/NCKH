from fastapi import APIRouter, Depends

from core.config import settings
from core.database import get_database
from core.dependencies import CurrentUser, require_admin
from modules.admin.overview_service import AdminOverviewService

router = APIRouter(prefix=f"{settings.api_prefix}/admin/overview", tags=["Admin overview"])


def get_admin_overview_service() -> AdminOverviewService:
    return AdminOverviewService(get_database())


@router.get("")
def get_admin_overview(
    _admin: CurrentUser = Depends(require_admin),
    service: AdminOverviewService = Depends(get_admin_overview_service),
):
    return service.overview()
