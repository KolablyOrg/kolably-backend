"""
Notification routes.
"""

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_current_user
from app.schemas.common import PaginatedResponse
from app.schemas.notification import NotificationResponse, UnreadCountResponse
from app.schemas.user import UserInToken
from app.services import notification_service

router = APIRouter()


@router.get("/", response_model=PaginatedResponse[NotificationResponse])
async def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: UserInToken = Depends(get_current_user),
):
    """List notifications for the current user."""
    return await notification_service.list_notifications(
        profile_id=user.id,
        page=page,
        page_size=page_size,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    user: UserInToken = Depends(get_current_user),
):
    """Get unread count for notifications."""
    return await notification_service.get_unread_count(profile_id=user.id)
