from fastapi import APIRouter, Depends, HTTPException, Query

from core.config import settings
from core.dependencies import CurrentUser, require_teacher_reviewer_or_admin
from modules.notifications.schemas import (
    NotificationListResponse,
    NotificationResponse,
    NotificationUnreadCountResponse,
)
from modules.notifications.service import NotificationService, get_notification_service

router = APIRouter(prefix=f"{settings.api_prefix}/notifications", tags=["Notifications"])


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
    current_user: CurrentUser = Depends(require_teacher_reviewer_or_admin),
    service: NotificationService = Depends(get_notification_service),
):
    return service.list(current_user, page, page_size, unread_only)


@router.get("/unread-count", response_model=NotificationUnreadCountResponse)
def unread_notification_count(
    current_user: CurrentUser = Depends(require_teacher_reviewer_or_admin),
    service: NotificationService = Depends(get_notification_service),
):
    return {"unread_count": service.unread_count(current_user)}


@router.post("/{notification_id}/read", response_model=NotificationResponse)
def mark_notification_read(
    notification_id: str,
    current_user: CurrentUser = Depends(require_teacher_reviewer_or_admin),
    service: NotificationService = Depends(get_notification_service),
):
    notification = service.mark_read(notification_id, current_user)
    if not notification:
        raise HTTPException(status_code=404, detail="Không tìm thấy thông báo")
    return notification


@router.post("/read-all")
def mark_all_notifications_read(
    current_user: CurrentUser = Depends(require_teacher_reviewer_or_admin),
    service: NotificationService = Depends(get_notification_service),
):
    return {"updated": service.mark_all_read(current_user)}
