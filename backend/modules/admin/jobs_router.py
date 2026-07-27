from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from core.config import settings
from core.database import get_database
from core.dependencies import CurrentUser, require_admin
from modules.admin.jobs_service import AdminJobService

router = APIRouter(prefix=f"{settings.api_prefix}/admin/jobs", tags=["Admin jobs"])


def get_admin_job_service() -> AdminJobService:
    return AdminJobService(get_database())


def _translate(exc: Exception):
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


@router.get("")
def list_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    kind: str | None = Query(None, pattern="^(generation|evaluation|document)$"),
    job_status: str | None = Query(None, alias="status"),
    user_id: str | None = None,
    stale_only: bool = False,
    search: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    _admin: CurrentUser = Depends(require_admin),
    service: AdminJobService = Depends(get_admin_job_service),
):
    try:
        return service.list_jobs(
            page=page,
            page_size=page_size,
            job_kind=kind,
            status=job_status,
            user_id=user_id,
            stale_only=stale_only,
            search=search,
            date_from=date_from,
            date_to=date_to,
        )
    except Exception as exc:
        _translate(exc)


@router.post("/{kind}/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_job(
    kind: str,
    job_id: str,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_admin),
    service: AdminJobService = Depends(get_admin_job_service),
):
    try:
        return service.retry_job(kind, job_id, background_tasks, current_user)
    except Exception as exc:
        _translate(exc)


@router.post("/{kind}/{job_id}/cancel")
def cancel_job(
    kind: str,
    job_id: str,
    current_user: CurrentUser = Depends(require_admin),
    service: AdminJobService = Depends(get_admin_job_service),
):
    try:
        return service.cancel_job(kind, job_id, current_user)
    except Exception as exc:
        _translate(exc)
