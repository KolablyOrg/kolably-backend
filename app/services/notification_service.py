from app.repositories.notification_repo import NotificationRepository


async def list_notifications(
    profile_id: str,
    page: int = 1,
    page_size: int = 20,
    *,
    repo: NotificationRepository | None = None,
) -> dict:
    repo = repo or NotificationRepository()
    rows, total = await repo.list_by_profile(
        profile_id=profile_id,
        page=page,
        page_size=page_size,
    )

    items = [
        {
            "id": row["id"],
            "profile_id": row["profile_id"],
            "type": row["type"],
            "title": row["title"],
            "body": row["body"],
            "related_id": row.get("related_id"),
            "is_read": row.get("is_read", False),
            "created_at": row["created_at"],
        }
        for row in rows
    ]

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
