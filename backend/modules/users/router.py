from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

from core.config import settings
from core.dependencies import CurrentUser, get_current_user, require_admin, require_teacher_or_admin
from modules.users.schemas import (
    CalendarResponse,
    GenerationPresetListResponse,
    GenerationPresetPayload,
    GenerationPresetResponse,
    RoleEnum,
    TaskCalendarPayload,
    TaskCalendarUpdateRequest,
    UserAdminUpdateRequest,
    UserCreateRequest,
    UserListResponse,
    UserResponse,
    UserSelfUpdateRequest,
    UserStatsResponse,
)
from modules.users.service import UserService, get_user_service

router = APIRouter(prefix=f"{settings.api_prefix}/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: CurrentUser = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    user = service.get(str(current_user.id))
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    return user


@router.patch("/me", response_model=UserResponse)
def update_me(
    payload: UserSelfUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    user = service.update_self(str(current_user.id), payload)
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    return user


@router.get("/me/stats", response_model=UserStatsResponse)
def get_my_stats(
    current_user: CurrentUser = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    stats = service.get_stats(str(current_user.id))
    if stats is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    return stats


@router.get("/me/generation-presets", response_model=GenerationPresetListResponse)
def list_my_generation_presets(
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    service: UserService = Depends(get_user_service),
):
    result = service.list_generation_presets(str(current_user.id))
    if result is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    return result


@router.post(
    "/me/generation-presets",
    response_model=GenerationPresetResponse,
    status_code=status.HTTP_201_CREATED,
)
def save_my_generation_preset(
    payload: GenerationPresetPayload,
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    service: UserService = Depends(get_user_service),
):
    preset = service.save_generation_preset(str(current_user.id), payload)
    if preset is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    return preset


@router.delete("/me/generation-presets/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_generation_preset(
    preset_id: str,
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    service: UserService = Depends(get_user_service),
):
    deleted = service.delete_generation_preset(str(current_user.id), preset_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    if not deleted:
        raise HTTPException(status_code=404, detail="Không tìm thấy mẫu cấu hình")


@router.get("/me/calendar", response_model=CalendarResponse)
def get_my_calendar(
    view: str = Query("agenda", pattern="^(month|week|agenda)$"),
    from_: date | None = Query(None, alias="from"),
    to: date | None = Query(None),
    status_filter: str = Query("all", alias="status"),
    priority: str = Query("all"),
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    service: UserService = Depends(get_user_service),
):
    date_from = datetime.combine(from_, datetime.min.time(), tzinfo=timezone.utc) if from_ else None
    date_to = datetime.combine(to, datetime.max.time(), tzinfo=timezone.utc) if to else None
    result = service.get_calendar(
        str(current_user.id),
        date_from=date_from,
        date_to=date_to,
        status=status_filter,
        priority=priority,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    return result


@router.post(
    "/me/calendar",
    status_code=status.HTTP_201_CREATED,
)
def create_my_calendar_task(
    payload: TaskCalendarPayload,
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    service: UserService = Depends(get_user_service),
):
    task = service.create_task(str(current_user.id), payload)
    if task is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    return task


@router.patch("/me/calendar/{event_id}")
def update_my_calendar_task(
    event_id: str,
    payload: TaskCalendarUpdateRequest,
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    service: UserService = Depends(get_user_service),
):
    result = service.update_task(str(current_user.id), event_id, payload)
    if result is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    if result is False:
        raise HTTPException(status_code=404, detail="Không tìm thấy việc cần làm")
    return result


@router.delete("/me/calendar/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_calendar_task(
    event_id: str,
    current_user: CurrentUser = Depends(require_teacher_or_admin),
    service: UserService = Depends(get_user_service),
):
    deleted = service.delete_task(str(current_user.id), event_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    if not deleted:
        raise HTTPException(status_code=404, detail="Không tìm thấy việc cần làm")


@router.get("", response_model=UserListResponse)
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    role: RoleEnum | None = None,
    search: str | None = None,
    _admin: CurrentUser = Depends(require_admin),
    service: UserService = Depends(get_user_service),
):
    return service.list(page, page_size, role.value if role else None, search)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest,
    _admin: CurrentUser = Depends(require_admin),
    service: UserService = Depends(get_user_service),
):
    try:
        return service.create_user(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: str,
    _admin: CurrentUser = Depends(require_admin),
    service: UserService = Depends(get_user_service),
):
    try:
        user = service.get(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    return user


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str,
    payload: UserAdminUpdateRequest,
    admin: CurrentUser = Depends(require_admin),
    service: UserService = Depends(get_user_service),
):
    try:
        user = service.update_admin(user_id, payload, admin)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: str,
    admin: CurrentUser = Depends(require_admin),
    service: UserService = Depends(get_user_service),
):
    try:
        deleted = service.deactivate(user_id, admin)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
