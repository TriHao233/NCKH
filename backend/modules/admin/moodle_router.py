from fastapi import APIRouter, Depends, HTTPException, Query, status

from core.config import settings
from core.database import get_database
from core.dependencies import CurrentUser, require_admin
from modules.admin.moodle_schemas import MoodleTargetPayload
from modules.admin.moodle_service import MoodleTargetService

router = APIRouter(prefix=f"{settings.api_prefix}/admin/moodle", tags=["Admin Moodle"])


def get_moodle_target_service() -> MoodleTargetService:
    return MoodleTargetService(get_database())


def _translate(exc: Exception):
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, RuntimeError) and str(exc) == "VERSION_CONFLICT":
        raise HTTPException(status_code=409, detail="Phiên bản câu hỏi đã thay đổi") from exc
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


@router.get("/targets")
def list_targets(
    include_inactive: bool = True,
    _admin: CurrentUser = Depends(require_admin),
    service: MoodleTargetService = Depends(get_moodle_target_service),
):
    return service.list_targets(include_inactive=include_inactive)


@router.post("/targets", status_code=status.HTTP_201_CREATED)
def save_target(
    payload: MoodleTargetPayload,
    current_user: CurrentUser = Depends(require_admin),
    service: MoodleTargetService = Depends(get_moodle_target_service),
):
    try:
        return service.save_target(payload, current_user)
    except Exception as exc:
        _translate(exc)


@router.post("/targets/{target_id}/check")
def check_target(
    target_id: str,
    current_user: CurrentUser = Depends(require_admin),
    service: MoodleTargetService = Depends(get_moodle_target_service),
):
    try:
        return service.check_target(target_id, current_user)
    except Exception as exc:
        _translate(exc)


@router.delete("/targets/{target_id}")
def deactivate_target(
    target_id: str,
    current_user: CurrentUser = Depends(require_admin),
    service: MoodleTargetService = Depends(get_moodle_target_service),
):
    try:
        return service.deactivate_target(target_id, current_user)
    except Exception as exc:
        _translate(exc)


@router.get("/publications")
def list_publications(
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    publication_status: str | None = Query(None, alias="status"),
    site_key: str | None = None,
    search: str | None = None,
    _admin: CurrentUser = Depends(require_admin),
    service: MoodleTargetService = Depends(get_moodle_target_service),
):
    return service.list_publications(
        page=page,
        page_size=page_size,
        status=publication_status,
        site_key=site_key,
        search=search,
    )


@router.post("/publications/{publication_id}/retry")
def retry_publication(
    publication_id: str,
    current_user: CurrentUser = Depends(require_admin),
    service: MoodleTargetService = Depends(get_moodle_target_service),
):
    try:
        return service.retry_publication(publication_id, current_user)
    except Exception as exc:
        _translate(exc)
