from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse

from core.config import resolve_path, settings
from core.dependencies import (
    CurrentUser,
    get_current_user,
    require_permissions,
    require_reviewer_or_admin,
    require_teacher_or_admin,
    require_teacher_reviewer_or_admin,
)
from modules.users.schemas import (
    CalendarResponse,
    GenerationPresetListResponse,
    GenerationPresetPayload,
    GenerationPresetResponse,
    RoleEnum,
    TaskCalendarPayload,
    TaskCalendarUpdateRequest,
    TeacherOptionListResponse,
    PasswordResetResponse,
    UserAdminUpdateRequest,
    UserCreateRequest,
    UserImportRequest,
    UserImportResponse,
    UserInviteRequest,
    UserInviteResponse,
    UserListResponse,
    UserResponse,
    UserSelfUpdateRequest,
    UserStatsResponse,
)
from modules.users.service import UserService, get_user_service

router = APIRouter(prefix=f"{settings.api_prefix}/users", tags=["Users"])

AVATAR_UPLOAD_DIR = resolve_path(settings.upload_dir) / "avatars"
AVATAR_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_AVATAR_BYTES = 2 * 1024 * 1024
AVATAR_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


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


@router.post("/me/avatar")
async def upload_my_avatar(
    request: Request,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    extension = AVATAR_CONTENT_TYPES.get(file.content_type or "")
    if not extension:
        raise HTTPException(status_code=400, detail="Vui lòng chọn ảnh JPG, PNG, WEBP hoặc GIF.")

    content = await file.read(MAX_AVATAR_BYTES + 1)
    if len(content) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=400, detail="Ảnh đại diện không vượt quá 2MB.")
    if not content:
        raise HTTPException(status_code=400, detail="File ảnh không hợp lệ.")

    filename = f"{current_user.id}-{uuid4().hex}{extension}"
    destination = AVATAR_UPLOAD_DIR / filename
    destination.write_bytes(content)
    base_url = str(request.base_url).rstrip("/")
    return {"avatar_url": f"{base_url}{settings.api_prefix}/users/avatar/{filename}"}


@router.get("/avatar/{filename}")
def get_avatar(filename: str):
    path = (AVATAR_UPLOAD_DIR / Path(filename).name).resolve()
    if not str(path).startswith(str(AVATAR_UPLOAD_DIR.resolve())) or not path.exists():
        raise HTTPException(status_code=404, detail="Không tìm thấy ảnh đại diện")
    return FileResponse(path)


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
    _admin: CurrentUser = Depends(require_permissions("admin.users")),
    service: UserService = Depends(get_user_service),
):
    return service.list(page, page_size, role.value if role else None, search)


@router.get("/teachers", response_model=TeacherOptionListResponse)
def list_teacher_options(
    search: str | None = None,
    _user: CurrentUser = Depends(require_teacher_reviewer_or_admin),
    service: UserService = Depends(get_user_service),
):
    return service.list_teacher_options(search)


@router.get("/reviewers", response_model=TeacherOptionListResponse)
def list_reviewer_options(
    search: str | None = None,
    _reviewer: CurrentUser = Depends(require_reviewer_or_admin),
    service: UserService = Depends(get_user_service),
):
    return service.list_reviewer_options(search)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest,
    _admin: CurrentUser = Depends(require_permissions("admin.users")),
    service: UserService = Depends(get_user_service),
):
    try:
        return service.create_user(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/invite", response_model=UserInviteResponse, status_code=status.HTTP_201_CREATED)
def invite_user(
    payload: UserInviteRequest,
    admin: CurrentUser = Depends(require_permissions("admin.users")),
    service: UserService = Depends(get_user_service),
):
    try:
        return service.invite_user(payload, admin)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/import", response_model=UserImportResponse)
def import_users(
    payload: UserImportRequest,
    admin: CurrentUser = Depends(require_permissions("admin.users")),
    service: UserService = Depends(get_user_service),
):
    return service.import_users(payload, admin)


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: str,
    _admin: CurrentUser = Depends(require_permissions("admin.users")),
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
    admin: CurrentUser = Depends(require_permissions("admin.users")),
    service: UserService = Depends(get_user_service),
):
    try:
        user = service.update_admin(user_id, payload, admin)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    return user


@router.post("/{user_id}/password-reset", response_model=PasswordResetResponse)
def reset_user_password(
    user_id: str,
    admin: CurrentUser = Depends(require_permissions("admin.users")),
    service: UserService = Depends(get_user_service),
):
    try:
        result = service.reset_password(user_id, admin)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    return result


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: str,
    admin: CurrentUser = Depends(require_permissions("admin.users")),
    service: UserService = Depends(get_user_service),
):
    try:
        deleted = service.deactivate(user_id, admin)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
