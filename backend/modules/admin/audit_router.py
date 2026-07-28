from datetime import datetime

from fastapi import APIRouter, Depends, Query

from core.config import settings
from core.database import get_database
from core.dependencies import CurrentUser, require_permissions
from modules.admin.audit_schemas import AuditLogListResponse
from modules.admin.audit_service import AdminAuditService

router = APIRouter(prefix=f"{settings.api_prefix}/admin/audit-logs", tags=["Admin audit"])


def get_admin_audit_service() -> AdminAuditService:
    return AdminAuditService(get_database())


@router.get("", response_model=AuditLogListResponse)
def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    actor_user_id: str | None = Query(None),
    entity_type: str | None = Query(None),
    entity_id: str | None = Query(None),
    action: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    search: str | None = Query(None),
    _admin: CurrentUser = Depends(require_permissions("admin.audit")),
    service: AdminAuditService = Depends(get_admin_audit_service),
):
    return service.list(
        page=page,
        page_size=page_size,
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )
