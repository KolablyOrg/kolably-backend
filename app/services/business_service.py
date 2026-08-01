from fastapi import HTTPException, status

from app.models.business import Business
from app.repositories.business_repo import BusinessRepository
from app.schemas.business import BusinessResponse, BusinessStatsResponse
from app.schemas.campaign import CampaignSummary


def _business_to_response(business: Business) -> BusinessResponse:
    """Single source of truth for mapping a Business model to a BusinessResponse.

    `user_id` is `profile_id` — the FK already IS the profile's id.
    """
    return BusinessResponse(
        id=business.id,
        user_id=business.profile_id,
        business_name=business.business_name,
        owner_name=business.owner_name,
        category=business.category,
        city=business.city,
        description=business.description,
        address=business.address,
        logo_url=business.logo_url,
        instagram_page=business.instagram_page,
        website=business.website,
        created_at=business.created_at,
        is_verified=business.is_verified,
    )


def _campaign_to_summary(campaign) -> CampaignSummary:
    """Convert a Campaign model to CampaignSummary schema."""
    return CampaignSummary(
        id=campaign.id,
        business_id=campaign.business_id,
        title=campaign.title,
        cover_image_url=campaign.cover_image_url,
        objective=campaign.objective,
        compensation_type=campaign.compensation_type,
        cash_amount_min=campaign.cash_amount_min,
        cash_amount_max=campaign.cash_amount_max,
        creator_category=campaign.creator_category,
        location=campaign.location,
        deadline=campaign.deadline,
        status=campaign.status,
        created_at=campaign.created_at,
        applicant_count=campaign.applicant_count,
    )


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
    businesses, total = await repo.list_filtered(
        search=search,
        category=category,
        city=city,
        page=page,
        page_size=page_size,
    )

    return {
        "items": [_business_to_response(b) for b in businesses],
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
    business = await repo.get_by_id(business_id)

    if not business:
        return None

    return _business_to_response(business)


async def list_business_campaigns(
    business_id: str,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
    *,
    repo: BusinessRepository | None = None,
) -> dict:
    repo = repo or BusinessRepository()
    campaigns, total = await repo.list_campaigns(
        business_id=business_id,
        status=status,
        page=page,
        page_size=page_size,
    )

    return {
        "items": [_campaign_to_summary(c) for c in campaigns],
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
) -> BusinessStatsResponse:
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

    return BusinessStatsResponse(
        total_reach=total_reach,
        reach_change_pct=0.0,
        avg_engagement_rate=0.0,
        engagement_series=[0.0] * 7,
    )
