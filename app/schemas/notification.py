"""
Notification Pydantic schemas.
"""

from datetime import datetime

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
