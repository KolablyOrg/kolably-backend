"""
Creator service — profile CRUD, discovery, Instagram integration.
"""

from fastapi import HTTPException, status

from app.core.supabase import get_supabase_admin_client
from app.schemas.creator import CreatorResponse


async def get_creator_by_id(creator_id: str) -> CreatorResponse | None:
    """Get a creator by ID with profile info."""
    admin_client = get_supabase_admin_client()

    result = (
        admin_client.table("creators")
        .select("*, profiles!creators_profile_id_fkey(email)")
        .eq("id", creator_id)
        .maybe_single()
        .execute()
    )

    if not result.data:
        return None

    data = result.data
    profile = data.pop("profiles", {})

    return CreatorResponse(
        id=data["id"],
        user_id=profile.get("id", data["profile_id"]),
        name=data["name"],
        username=data.get("username"),
        profile_photo_url=data.get("profile_photo_url"),
        niche=data.get("niche"),
        city=data.get("city"),
        follower_count=data.get("follower_count"),
        engagement_rate=data.get("engagement_rate"),
        bio=data.get("bio"),
        created_at=data["created_at"],
        tiktok_handle=data.get("tiktok_handle"),
        instagram_connected=bool(data.get("instagram_user_id") and data.get("instagram_access_token")),
        instagram_synced_at=data.get("instagram_synced_at"),
    )


async def list_creators(
    search: str | None = None,
    niche: str | None = None,
    city: str | None = None,
    follower_min: int | None = None,
    follower_max: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """List and filter creators with pagination."""
    admin_client = get_supabase_admin_client()

    query = admin_client.table("creators").select("*", count="exact")

    if search:
        query = query.ilike("name", f"%{search}%")
    if niche:
        query = query.eq("niche", niche)
    if city:
        query = query.ilike("city", f"%{city}%")
    if follower_min is not None:
        query = query.gte("follower_count", follower_min)
    if follower_max is not None:
        query = query.lte("follower_count", follower_max)

    start = (page - 1) * page_size
    end = start + page_size - 1
    result = query.range(start, end).execute()

    rows = result.data or []
    items = []
    for row in rows:
        items.append({
            "id": row["id"],
            "user_id": row.get("profile_id"),
            "name": row["name"],
            "username": row.get("username"),
            "profile_photo_url": row.get("profile_photo_url"),
            "niche": row.get("niche"),
            "city": row.get("city"),
            "follower_count": row.get("follower_count"),
            "engagement_rate": row.get("engagement_rate"),
            "bio": row.get("bio"),
            "created_at": row["created_at"],
            "tiktok_handle": row.get("tiktok_handle"),
            "instagram_connected": bool(row.get("instagram_user_id") and row.get("instagram_access_token")),
            "instagram_synced_at": row.get("instagram_synced_at"),
        })

    return {
        "items": items,
        "total": result.count or 0,
        "page": page,
        "page_size": page_size,
    }


async def get_creator_portfolio(
    creator_id: str,
    media_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Get portfolio items for a creator."""
    admin_client = get_supabase_admin_client()

    query = (
        admin_client.table("portfolio_items")
        .select("*", count="exact")
        .eq("creator_id", creator_id)
    )

    if media_type:
        query = query.eq("media_type", media_type)

    start = (page - 1) * page_size
    end = start + page_size - 1
    result = query.range(start, end).execute()

    rows = result.data or []
    items = []
    for row in rows:
        items.append({
            "id": row["id"],
            "creator_id": row["creator_id"],
            "media_url": row["media_url"],
            "post_link": row.get("post_link"),
            "caption": row.get("caption"),
            "media_type": row.get("media_type", "photo"),
            "like_count": row.get("like_count"),
            "comment_count": row.get("comment_count"),
            "created_at": row["created_at"],
        })

    return {
        "items": items,
        "total": result.count or 0,
        "page": page,
        "page_size": page_size,
    }


async def get_creator_stats(profile_id: str) -> dict:
    """Get creator stats: active_collaborations_count."""
    admin_client = get_supabase_admin_client()

    creator_result = (
        admin_client.table("creators")
        .select("id")
        .eq("profile_id", profile_id)
        .maybe_single()
        .execute()
    )
    if not creator_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator profile not found",
        )

    creator_id = creator_result.data["id"]

    collabs_result = (
        admin_client.table("collaborations")
        .select("id", count="exact")
        .eq("creator_id", creator_id)
        .eq("status", "active")
        .execute()
    )

    return {
        "active_collaborations_count": collabs_result.count or 0,
        "engagement_growth_pct": None,
    }


async def list_saved_campaigns(
    profile_id: str,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """List saved campaigns for a creator."""
    admin_client = get_supabase_admin_client()

    creator_result = (
        admin_client.table("creators")
        .select("id")
        .eq("profile_id", profile_id)
        .maybe_single()
        .execute()
    )
    if not creator_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator profile not found",
        )

    creator_id = creator_result.data["id"]

    query = (
        admin_client.table("saved_campaigns")
        .select("*, campaigns!saved_campaigns_campaign_id_fkey(*)", count="exact")
        .eq("creator_id", creator_id)
    )

    start = (page - 1) * page_size
    end = start + page_size - 1
    result = query.range(start, end).execute()

    items = []
    for row in result.data or []:
        campaign = row.get("campaigns", {})
        if campaign:
            items.append({
                "id": campaign.get("id"),
                "business_id": campaign.get("business_id"),
                "title": campaign.get("title"),
                "cover_image_url": campaign.get("cover_image_url"),
                "objective": campaign.get("objective"),
                "compensation_type": campaign.get("compensation_type"),
                "cash_amount_min": campaign.get("cash_amount_min"),
                "cash_amount_max": campaign.get("cash_amount_max"),
                "creator_category": campaign.get("creator_category"),
                "location": campaign.get("location"),
                "deadline": campaign.get("deadline"),
                "status": campaign.get("status"),
                "created_at": campaign.get("created_at"),
            })

    return {
        "items": items,
        "total": result.count or 0,
        "page": page,
        "page_size": page_size,
    }
