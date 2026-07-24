from fastapi import APIRouter, Depends, HTTPException, Query, status

from core.config import settings
from core.dependencies import CurrentUser, get_current_user, require_admin
from modules.users.schemas import (
    RoleEnum,
    UserAdminUpdateRequest,
    UserCreateRequest,
    UserListResponse,
    UserResponse,
    UserSelfUpdateRequest,
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
    _admin: CurrentUser = Depends(require_admin),
    service: UserService = Depends(get_user_service),
):
    try:
        user = service.update_admin(user_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: str,
    _admin: CurrentUser = Depends(require_admin),
    service: UserService = Depends(get_user_service),
):
    try:
        deleted = service.deactivate(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
