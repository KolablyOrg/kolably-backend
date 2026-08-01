from app.models.notification import Notification
from app.repositories.notification_repo import NotificationRepository


def _notification_to_response(notif: Notification) -> dict:
    """Convert a Notification model to a response dict."""
    return {
        "id": notif.id,
        "profile_id": notif.user_id,
        "type": notif.type.value if hasattr(notif.type, "value") else notif.type,
        "title": notif.title,
        "body": notif.body,
        "related_id": notif.data.get("related_id"),
        "is_read": notif.read_at is not None,
        "created_at": notif.created_at,
    }


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
