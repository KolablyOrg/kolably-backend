"""
Notification Pydantic schemas.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.core.enums import NotificationType


class NotificationResponse(BaseModel):
    id: str
    profile_id: str
    type: NotificationType
    title: str
    body: str
    related_id: str | None = None
    is_read: bool = False
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int
    page: int
    page_size: int


class UnreadCountResponse(BaseModel):
    unread_count: int


class RegisterPushTokenRequest(BaseModel):
    token: str
    platform: Literal["ios", "android"]


class TestPushReceipt(BaseModel):
    """One device's result from Expo. `token` is truncated on purpose."""

    token: str
    status: str | None = None
    error: str | None = None
    message: str | None = None


class TestPushResponse(BaseModel):
    """Diagnostic result of POST /notifications/test-push.

    `sent` means Expo accepted the message for at least one device — it does
    NOT mean a notification appeared. That distinction is the whole point of
    this endpoint: it separates "the server never had a device to send to"
    from "the server sent it and something downstream ate it."
    """

    sent: bool
    devices: int
    detail: str
    receipts: list[TestPushReceipt] = []
