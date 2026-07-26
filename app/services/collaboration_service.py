"""
Collaboration service — lifecycle management, content submission, completion.
"""

from fastapi import HTTPException, status

from app.core.supabase import get_supabase_admin_client


def _get_creator_id_for_user(admin_client, profile_id: str) -> str:
    """Look up `creators.id` from `profiles.id`."""
    result = (
        admin_client.table("creators")
        .select("id")
        .eq("profile_id", profile_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator profile not found",
        )
    return result.data["id"]


def _get_business_id_for_user(admin_client, profile_id: str) -> str:
    """Look up `businesses.id` from `profiles.id`."""
    result = (
        admin_client.table("businesses")
        .select("id")
        .eq("profile_id", profile_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found",
        )
    return result.data["id"]


def _ensure_collaboration_exists(admin_client, collaboration_id: str) -> dict:
    """Fetch a collaboration and verify it exists. Returns the row."""
    result = (
        admin_client.table("collaborations")
        .select("*")
        .eq("id", collaboration_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collaboration not found",
        )
    return result.data


def _row_to_collaboration_response(row: dict) -> dict:
    """Convert a Supabase collaborations row to a CollaborationResponse dict."""
    return {
        "id": row["id"],
        "campaign_id": row["campaign_id"],
        "creator_id": row["creator_id"],
        "business_id": row["business_id"],
        "status": row["status"],
        "content_submissions": [],
        "affiliate_url": row.get("affiliate_url"),
        "created_at": row["created_at"],
        "completed_at": row.get("completed_at"),
    }


async def list_collaborations(
    profile_id: str,
    role: str,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """List collaborations for the current user (filtered by role)."""
    admin_client = get_supabase_admin_client()

    query = admin_client.table("collaborations").select("*", count="exact")

    if role == "creator":
        creator_id = _get_creator_id_for_user(admin_client, profile_id)
        query = query.eq("creator_id", creator_id)
    elif role == "business":
        business_id = _get_business_id_for_user(admin_client, profile_id)
        query = query.eq("business_id", business_id)
    else:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    start = (page - 1) * page_size
    end = start + page_size - 1
    result = query.range(start, end).execute()

    items = []
    for row in result.data or []:
        items.append(_row_to_collaboration_response(row))

    return {
        "items": items,
        "total": result.count or 0,
        "page": page,
        "page_size": page_size,
    }


async def get_collaboration(collaboration_id: str) -> dict:
    """Get collaboration details."""
    admin_client = get_supabase_admin_client()
    row = _ensure_collaboration_exists(admin_client, collaboration_id)

    subs_result = (
        admin_client.table("content_submissions")
        .select("*")
        .eq("collaboration_id", collaboration_id)
        .execute()
    )
    submissions = []
    for sub in subs_result.data or []:
        submissions.append({
            "id": sub["id"],
            "collaboration_id": sub["collaboration_id"],
            "content_url": sub["content_url"],
            "platform": sub["platform"],
            "views": sub.get("views"),
            "likes": sub.get("likes"),
            "comments": sub.get("comments"),
            "synced_at": sub.get("synced_at"),
            "submitted_at": sub["submitted_at"],
        })

    resp = _row_to_collaboration_response(row)
    resp["content_submissions"] = submissions
    return resp
