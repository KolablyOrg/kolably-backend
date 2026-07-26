"""
Notification service — get, mark read.
"""


from app.core.supabase import get_supabase_admin_client


async def list_notifications(
    profile_id: str,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """List notifications for the current user."""
    admin_client = get_supabase_admin_client()

    query = (
        admin_client.table("notifications")
        .select("*", count="exact")
        .eq("profile_id", profile_id)
    )

    start = (page - 1) * page_size
    end = start + page_size - 1
    result = query.range(start, end).execute()

    items = []
    for row in result.data or []:
        items.append({
            "id": row["id"],
            "profile_id": row["profile_id"],
            "type": row["type"],
            "title": row["title"],
            "body": row["body"],
            "related_id": row.get("related_id"),
            "is_read": row.get("is_read", False),
            "created_at": row["created_at"],
        })

    return {
        "items": items,
        "total": result.count or 0,
        "page": page,
        "page_size": page_size,
    }


async def get_unread_count(profile_id: str) -> dict:
    """Get unread count for the current user."""
    admin_client = get_supabase_admin_client()

    result = (
        admin_client.table("notifications")
        .select("id", count="exact")
        .eq("profile_id", profile_id)
        .eq("is_read", False)
        .execute()
    )

    return {"unread_count": result.count or 0}
