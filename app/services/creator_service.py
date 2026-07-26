from fastapi import HTTPException, status

from app.repositories.creator_repo import CreatorRepository
from app.schemas.creator import CreatorResponse


async def get_creator_by_id(creator_id: str) -> CreatorResponse | None:
    repo = CreatorRepository()
    data = await repo.get_by_id(creator_id)

    if not data:
        return None

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
    repo = CreatorRepository()
    rows, total = await repo.list_filtered(
        search=search,
        niche=niche,
        city=city,
        follower_min=follower_min,
        follower_max=follower_max,
        page=page,
        page_size=page_size,
    )

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
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_creator_portfolio(
    creator_id: str,
    media_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    repo = CreatorRepository()
    rows, total = await repo.list_portfolio(
        creator_id=creator_id,
        media_type=media_type,
        page=page,
        page_size=page_size,
    )

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
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_creator_stats(profile_id: str) -> dict:
    repo = CreatorRepository()
    creator_id = await repo.get_id_by_profile_id(profile_id)

    if not creator_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator profile not found",
        )

    active_count = await repo.count_active_collaborations(creator_id)

    return {
        "active_collaborations_count": active_count,
        "engagement_growth_pct": None,
    }


async def list_saved_campaigns(
    profile_id: str,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    repo = CreatorRepository()
    creator_id = await repo.get_id_by_profile_id(profile_id)

    if not creator_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator profile not found",
        )

    rows, total = await repo.list_saved_campaigns(
        creator_id=creator_id,
        page=page,
        page_size=page_size,
    )

    items = []
    for row in rows:
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
        "total": total,
        "page": page,
        "page_size": page_size,
    }
