"""
Notification routes.
"""

from fastapi import APIRouter, Depends, Query, Request

from app.core.dependencies import get_current_user
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.notification import (
    NotificationResponse,
    RegisterPushTokenRequest,
    TestPushResponse,
    UnreadCountResponse,
)
from app.schemas.user import UserInToken
from app.services import email_service, notification_service, push_notification_service

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


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: str,
    user: UserInToken = Depends(get_current_user),
):
    """Mark a single notification as read."""
    return await notification_service.mark_notification_read(
        notification_id=notification_id,
        profile_id=user.id,
    )


@router.patch("/read-all", response_model=MessageResponse)
async def mark_all_notifications_read(
    user: UserInToken = Depends(get_current_user),
):
    """Mark all of the current user's notifications as read."""
    return await notification_service.mark_all_notifications_read(profile_id=user.id)


@router.post("/register-token", response_model=MessageResponse)
async def register_push_token(
    body: RegisterPushTokenRequest,
    user: UserInToken = Depends(get_current_user),
):
    """Register (or reassign) an Expo push token for the current user's device."""
    await push_notification_service.register_token(user.id, body.token, body.platform)
    return {"message": "Push token registered"}


@router.post("/test-push", response_model=TestPushResponse)
async def send_test_push(
    user: UserInToken = Depends(get_current_user),
):
    """Send a test push to the caller's own registered devices.

    Only ever targets `user.id` — there is no recipient parameter, so this
    cannot be used to push to anyone else.

    Unlike every other push in this app, this one reports what happened:
    how many devices are registered and Expo's per-token receipt. "No
    notification arrived" is otherwise unfalsifiable from the client side.
    """
    return await push_notification_service.send_test_push(user.id)


@router.delete("/register-token", response_model=MessageResponse)
async def unregister_push_token(
    token: str = Query(...),
    user: UserInToken = Depends(get_current_user),
):
    """Remove a device's push token, e.g. on logout. Not ownership-checked —
    a token that isn't this user's (or doesn't exist) is a no-op either way."""
    await push_notification_service.unregister_token(token)
    return {"message": "Push token unregistered"}


@router.post("/webhooks/resend")
async def resend_webhook(request: Request):
    """Process delivery webhook events from Resend (delivered, bounced, complained)."""
    payload = await request.json()
    return await email_service.handle_resend_webhook(payload)
