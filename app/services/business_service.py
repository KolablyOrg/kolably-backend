from fastapi import HTTPException, status

from app.repositories.business_repo import BusinessRepository
from app.schemas.business import BusinessResponse


def _row_to_business_response(row: dict) -> BusinessResponse:
    """Single source of truth for mapping a `businesses` row to a BusinessResponse.

    `user_id` is `profile_id` — the FK already IS the profile's id.
    """
    return BusinessResponse(
        id=row["id"],
        user_id=row["profile_id"],
        business_name=row["business_name"],
        owner_name=row.get("owner_name", ""),
        category=row.get("category", ""),
        city=row.get("city", ""),
        description=row.get("description"),
        address=row.get("address"),
        logo_url=row.get("logo_url"),
        instagram_page=row.get("instagram_page"),
        website=row.get("website"),
        created_at=row["created_at"],
        is_verified=row.get("is_verified", False),
    )


def _row_to_campaign_summary(row: dict) -> dict:
    return {
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
    }


async def _get_business_id_for_user(
    profile_id: str,
    *,
    repo: BusinessRepository | None = None,
) -> str:
    repo = repo or BusinessRepository()
    business_id = await repo.get_id_by_profile_id(profile_id)
    if not business_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found",
        )
    return business_id


async def list_businesses(
    search: str | None = None,
    category: str | None = None,
    city: str | None = None,
    page: int = 1,
    page_size: int = 20,
    *,
    repo: BusinessRepository | None = None,
) -> dict:
    repo = repo or BusinessRepository()
    rows, total = await repo.list_filtered(
        search=search,
        category=category,
        city=city,
        page=page,
        page_size=page_size,
    )

    return {
        "items": [_row_to_business_response(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_business_by_id(
    business_id: str,
    *,
    repo: BusinessRepository | None = None,
) -> BusinessResponse | None:
    repo = repo or BusinessRepository()
    row = await repo.get_by_id(business_id)

    if not row:
        return None

    return _row_to_business_response(row)


async def list_business_campaigns(
    business_id: str,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
    *,
    repo: BusinessRepository | None = None,
) -> dict:
    repo = repo or BusinessRepository()
    rows, total = await repo.list_campaigns(
        business_id=business_id,
        status=status,
        page=page,
        page_size=page_size,
    )

    return {
        "items": [_row_to_campaign_summary(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def list_my_campaigns(
    profile_id: str,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
    *,
    repo: BusinessRepository | None = None,
) -> dict:
    """Campaigns belonging to the caller's own business."""
    repo = repo or BusinessRepository()
    business_id = await _get_business_id_for_user(profile_id, repo=repo)
    return await list_business_campaigns(
        business_id=business_id,
        status=status,
        page=page,
        page_size=page_size,
        repo=repo,
    )


async def get_business_stats(
    profile_id: str,
    *,
    repo: BusinessRepository | None = None,
) -> dict:
    repo = repo or BusinessRepository()
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
