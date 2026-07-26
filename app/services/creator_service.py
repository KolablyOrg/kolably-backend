from fastapi import HTTPException, status

from app.repositories.creator_repo import CreatorRepository
from app.schemas.creator import CreatorResponse


def _row_to_creator_response(row: dict) -> CreatorResponse:
    """Single source of truth for mapping a `creators` row to a CreatorResponse.

    `user_id` is `profile_id` — the FK already IS the profile's id.
    """
    return CreatorResponse(
        id=row["id"],
        user_id=row["profile_id"],
        name=row["name"],
        username=row.get("username"),
        profile_photo_url=row.get("profile_photo_url"),
        niche=row.get("niche"),
        city=row.get("city"),
        follower_count=row.get("follower_count"),
        engagement_rate=row.get("engagement_rate"),
        bio=row.get("bio"),
        created_at=row["created_at"],
        tiktok_handle=row.get("tiktok_handle"),
        instagram_connected=bool(row.get("instagram_user_id") and row.get("instagram_access_token")),
        instagram_synced_at=row.get("instagram_synced_at"),
    )


async def get_creator_by_id(
    creator_id: str,
    *,
    repo: CreatorRepository | None = None,
) -> CreatorResponse | None:
    repo = repo or CreatorRepository()
    row = await repo.get_by_id(creator_id)

    if not row:
        return None

    return _row_to_creator_response(row)


async def list_creators(
    search: str | None = None,
    niche: str | None = None,
    city: str | None = None,
    follower_min: int | None = None,
    follower_max: int | None = None,
    page: int = 1,
    page_size: int = 20,
    *,
    repo: CreatorRepository | None = None,
) -> dict:
    repo = repo or CreatorRepository()
    rows, total = await repo.list_filtered(
        search=search,
        niche=niche,
        city=city,
        follower_min=follower_min,
        follower_max=follower_max,
        page=page,
        page_size=page_size,
    )

    return {
        "items": [_row_to_creator_response(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_creator_portfolio(
    creator_id: str,
    media_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
    *,
    repo: CreatorRepository | None = None,
) -> dict:
    repo = repo or CreatorRepository()
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


async def get_creator_stats(
    profile_id: str,
    *,
    repo: CreatorRepository | None = None,
) -> dict:
    repo = repo or CreatorRepository()
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
    *,
    repo: CreatorRepository | None = None,
) -> dict:
    repo = repo or CreatorRepository()
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
