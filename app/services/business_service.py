from fastapi import HTTPException, status

from app.repositories.business_repo import BusinessRepository
from app.schemas.business import BusinessResponse


async def list_businesses(
    search: str | None = None,
    category: str | None = None,
    city: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    repo = BusinessRepository()
    rows, total = await repo.list_filtered(
        search=search,
        category=category,
        city=city,
        page=page,
        page_size=page_size,
    )

    items = []
    for row in rows:
        items.append({
            "id": row["id"],
            "user_id": row.get("profile_id"),
            "business_name": row["business_name"],
            "owner_name": row.get("owner_name", ""),
            "category": row.get("category", ""),
            "city": row.get("city", ""),
            "description": row.get("description"),
            "address": row.get("address"),
            "logo_url": row.get("logo_url"),
            "instagram_page": row.get("instagram_page"),
            "website": row.get("website"),
            "created_at": row["created_at"],
            "is_verified": row.get("is_verified", False),
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_business_by_id(business_id: str) -> BusinessResponse | None:
    repo = BusinessRepository()
    data = await repo.get_by_id(business_id)

    if not data:
        return None

    profile = data.pop("profiles", {})

    return BusinessResponse(
        id=data["id"],
        user_id=profile.get("id", data["profile_id"]),
        business_name=data["business_name"],
        owner_name=data.get("owner_name", ""),
        category=data.get("category", ""),
        city=data.get("city", ""),
        description=data.get("description"),
        address=data.get("address"),
        logo_url=data.get("logo_url"),
        instagram_page=data.get("instagram_page"),
        website=data.get("website"),
        created_at=data["created_at"],
        is_verified=data.get("is_verified", False),
    )


async def list_business_campaigns(
    business_id: str,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    repo = BusinessRepository()
    rows, total = await repo.list_campaigns(
        business_id=business_id,
        status=status,
        page=page,
        page_size=page_size,
    )

    items = []
    for row in rows:
        items.append({
            "id": row["id"],
            "business_id": row["business_id"],
            "title": row["title"],
            "cover_image_url": row.get("cover_image_url"),
            "objective": row.get("objective"),
            "compensation_type": row.get("compensation_type"),
            "cash_amount_min": row.get("cash_amount_min"),
            "cash_amount_max": row.get("cash_amount_max"),
            "creator_category": row.get("creator_category", ""),
            "location": row.get("location", ""),
            "deadline": row.get("deadline"),
            "status": row["status"],
            "created_at": row["created_at"],
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_business_stats(profile_id: str) -> dict:
    repo = BusinessRepository()
    business_id = await repo.get_id_by_profile_id(profile_id)

    if not business_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found",
        )

    campaign_ids = await repo.get_campaign_ids(business_id)

    total_reach = 0
    if campaign_ids:
        collab_ids = await repo.get_collab_ids_for_campaigns(campaign_ids)
        if collab_ids:
            subs = await repo.get_submissions_for_collabs(collab_ids)
            for sub in subs:
                total_reach += sub.get("views", 0) or 0

    return {
        "total_reach": total_reach,
        "reach_change_pct": 0.0,
        "avg_engagement_rate": 0.0,
        "engagement_series": [0.0] * 7,
    }
