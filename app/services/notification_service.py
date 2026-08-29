import logging

from fastapi import HTTPException, status

from app.core.enums import NotificationType
from app.models.notification import Notification
from app.repositories.notification_repo import NotificationRepository
from app.services import push_notification_service


def _notification_to_response(notif: Notification) -> dict:
    """Convert a Notification model to a response dict."""
    return {
        "id": notif.id,
        "profile_id": notif.profile_id,
        "type": notif.type.value if hasattr(notif.type, "value") else notif.type,
        "title": notif.title,
        "body": notif.body,
        "related_id": notif.related_id,
        "is_read": notif.is_read,
        "created_at": notif.created_at,
    }


async def create_notification(
    profile_id: str,
    type: NotificationType,
    title: str,
    body: str,
    related_id: str | None = None,
    *,
    repo: NotificationRepository | None = None,
) -> None:
    """Fire-and-forget notification producer, used as a side effect by other services.

    Never raises — a notification failing to write shouldn't fail the action
    that triggered it (an accepted application, a sent message, etc.).
    """
    repo = repo or NotificationRepository()
    try:
        await repo.insert_notification({
            "profile_id": profile_id,
            "type": type.value,
            "title": title,
            "body": body,
            "related_id": related_id,
        })
    except Exception:
        logging.getLogger(__name__).exception(
            "Failed to create notification (profile_id=%s, type=%s)", profile_id, type.value
        )
        return

    # Fan out to every device this profile has push enabled on. Has its own
    # never-raise contract — a push failing to send must not undo, or even
    # surface as an error on, the in-app notification write above.
    await push_notification_service.send_push_to_profile(
        profile_id,
        title,
        body,
        data={"type": type.value, "related_id": related_id},
    )


async def list_notifications(
    profile_id: str,
    page: int = 1,
    page_size: int = 20,
    *,
    repo: NotificationRepository | None = None,
) -> dict:
    repo = repo or NotificationRepository()
    notifications, total = await repo.list_by_profile(
        profile_id=profile_id,
        page=page,
        page_size=page_size,
    )

    items = [_notification_to_response(n) for n in notifications]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_unread_count(
    profile_id: str,
    *,
    repo: NotificationRepository | None = None,
) -> dict:
    repo = repo or NotificationRepository()
    count = await repo.count_unread(profile_id)
    return {"unread_count": count}


async def mark_notification_read(
    notification_id: str,
    profile_id: str,
    *,
    repo: NotificationRepository | None = None,
) -> dict:
    repo = repo or NotificationRepository()
    notif = await repo.mark_read(notification_id, profile_id)
    if not notif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    return _notification_to_response(notif)


async def mark_all_notifications_read(
    profile_id: str,
    *,
    repo: NotificationRepository | None = None,
) -> dict:
    repo = repo or NotificationRepository()
    await repo.mark_all_read(profile_id)
    return {"message": "All notifications marked as read"}
