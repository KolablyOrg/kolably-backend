from typing import Any

from fastapi import HTTPException, status

from app.core.enums import (
    ApplicationDirection,
    ApplicationStatus,
    CampaignStatus,
    InvoiceStatus,
    NotificationType,
    UserRole,
)
from app.models.campaign import Campaign
from app.repositories.application_repo import ApplicationRepository
from app.repositories.business_member_repo import BusinessMemberRepository
from app.repositories.business_repo import BusinessRepository
from app.repositories.campaign_repo import CampaignRepository
from app.repositories.collaboration_repo import CollaborationRepository
from app.repositories.creator_repo import CreatorRepository
from app.repositories.invoice_repo import InvoiceRepository
from app.schemas.application import ApplicationResponse, ApplicationWithCreator
from app.schemas.campaign import (
    BudgetBoundsResponse,
    CampaignAnalyticsResponse,
    CampaignCategoryResponse,
    CampaignCreateRequest,
    CampaignDeliverablesRequest,
    CampaignResponse,
    CampaignSummary,
    CampaignTargetingRequest,
    CampaignUpdateRequest,
)
from app.schemas.creator import CreatorSummary
from app.schemas.user import UserInToken
from app.services import business_access, notification_service


def _campaign_to_response(campaign: Campaign) -> CampaignResponse:
    """Convert Campaign model to CampaignResponse schema."""
    return CampaignResponse(
        id=campaign.id,
        business_id=campaign.business_id,
        title=campaign.title,
        objective=campaign.objective,
        description=campaign.description,
        cover_image_url=campaign.cover_image_url,
        deliverables=[d.to_dict() for d in campaign.deliverables],
        compensation_type=campaign.compensation_type,
        cash_amount_min=campaign.cash_amount_min,
        cash_amount_max=campaign.cash_amount_max,
        free_product_description=campaign.free_product_description,
        creator_category=campaign.creator_category,
        follower_range_min=campaign.follower_range_min,
        follower_range_max=campaign.follower_range_max,
        min_engagement_rate=campaign.min_engagement_rate,
        location=campaign.location,
        max_creators=campaign.max_creators,
        additional_requirements=campaign.additional_requirements,
        deadline=campaign.deadline,
        status=campaign.status,
        created_at=campaign.created_at,
        applicant_count=campaign.applicant_count,
        accepted_count=campaign.accepted_count,
        posted_count=campaign.posted_count,
        platforms=list(campaign.platforms or []),
        product_promoted=campaign.product_promoted,
        audience_age_range=campaign.audience_age_range,
        audience_gender=campaign.audience_gender,
        audience_location=campaign.audience_location,
        audience_interests=campaign.audience_interests,
        key_messaging=campaign.key_messaging,
        dos=campaign.dos,
        donts=campaign.donts,
        reference_image_urls=list(campaign.reference_image_urls or []),
        content_due_at=campaign.content_due_at,
    )


def _campaign_to_summary(
    campaign: Campaign,
    *,
    business_name: str | None = None,
    business_logo_url: str | None = None,
    is_verified: bool | None = None,
) -> CampaignSummary:
    """Convert Campaign model to CampaignSummary schema."""
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
        accepted_count=campaign.accepted_count,
        max_creators=campaign.max_creators,
        business_name=business_name,
        business_logo_url=business_logo_url,
        is_verified=is_verified,
    )


def _category_values_matching_search(term: str) -> list[str]:
    """Map free-text search onto category values via label/value match."""
    needle = term.strip().lower()
    if not needle:
        return []
    matches: list[str] = []
    for cat in CAMPAIGN_CATEGORIES:
        label = cat.label.lower()
        if needle == cat.value or needle == label:
            matches.append(cat.value)
        elif len(needle) >= 3 and (needle in label or cat.value.startswith(needle)):
            matches.append(cat.value)
    return matches


def _niche_to_category(niche: str) -> str | None:
    """Map a creator niche (label or value) to a campaign category enum value."""
    matches = _category_values_matching_search(niche)
    return matches[0] if matches else None


async def _get_business_id_for_user(
    profile_id: str,
    *,
    repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> str:
    business_id = await business_access.get_business_id_for_profile(
        profile_id, business_repo=repo, member_repo=member_repo
    )
    if not business_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found",
        )
    return business_id


async def _can_view_draft_campaign(
    campaign: Campaign,
    user: UserInToken | None,
    *,
    business_repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> bool:
    """Draft campaigns are visible only to the owning business (incl. its
    team members) or superadmin."""
    if not user:
        return False
    if user.role == UserRole.SUPERADMIN:
        return True
    business_id = await business_access.get_business_id_for_profile(
        user.id, business_repo=business_repo, member_repo=member_repo
    )
    return business_id is not None and campaign.business_id == business_id


async def _ensure_campaign_owner(
    campaign_repo: CampaignRepository,
    campaign_id: str,
    business_id: str,
    profile_id: str,
    *,
    require_write: bool = True,
    business_repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> Campaign:
    campaign = await campaign_repo.get_by_id(campaign_id)
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )
    if campaign.business_id != business_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this campaign",
        )
    if require_write:
        await business_access.require_write_access(
            business_id, profile_id, business_repo=business_repo, member_repo=member_repo
        )
    return campaign


async def create_campaign_step1(
    profile_id: str,
    data: CampaignCreateRequest,
    *,
    campaign_repo: CampaignRepository | None = None,
    business_repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> CampaignResponse:
    business_id = await _get_business_id_for_user(profile_id, repo=business_repo, member_repo=member_repo)
    await business_access.require_write_access(
        business_id, profile_id, business_repo=business_repo, member_repo=member_repo
    )
    campaign_repo = campaign_repo or CampaignRepository()

    insert_data = {
        "business_id": business_id,
        "title": data.title,
        "objective": data.objective.value,
        "description": data.description,
        "status": CampaignStatus.DRAFT.value,
        "deliverables": [],
        "creator_category": "",
        "location": "",
        "max_creators": 1,
    }

    campaign = await campaign_repo.insert_campaign(insert_data)
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create campaign",
        )

    return _campaign_to_response(campaign)


async def update_campaign_deliverables(
    campaign_id: str,
    profile_id: str,
    data: CampaignDeliverablesRequest,
    *,
    campaign_repo: CampaignRepository | None = None,
    business_repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> CampaignResponse:
    business_id = await _get_business_id_for_user(profile_id, repo=business_repo, member_repo=member_repo)
    campaign_repo = campaign_repo or CampaignRepository()
    await _ensure_campaign_owner(
        campaign_repo, campaign_id, business_id, profile_id, business_repo=business_repo, member_repo=member_repo,
    )

    update_data: dict[str, Any] = {
        "deliverables": [d.model_dump(mode="json") for d in data.deliverables],
        "compensation_type": data.compensation_type.value,
        # Always write cash/perk fields (including null) so switching to
        # product-only clears stale cash_amount_min/max from a prior cash offer.
        "cash_amount_min": data.cash_amount_min,
        "cash_amount_max": data.cash_amount_max,
        "free_product_description": data.free_product_description,
    }

    campaign = await campaign_repo.update_campaign(campaign_id, update_data)
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    return _campaign_to_response(campaign)


async def update_campaign_targeting(
    campaign_id: str,
    profile_id: str,
    data: CampaignTargetingRequest,
    *,
    campaign_repo: CampaignRepository | None = None,
    business_repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> CampaignResponse:
    business_id = await _get_business_id_for_user(profile_id, repo=business_repo, member_repo=member_repo)
    campaign_repo = campaign_repo or CampaignRepository()
    await _ensure_campaign_owner(
        campaign_repo, campaign_id, business_id, profile_id, business_repo=business_repo, member_repo=member_repo,
    )

    # mode="json" so enums/datetimes are JSON-safe for PostgREST.
    update_data: dict[str, Any] = data.model_dump(mode="json", exclude_none=True)

    campaign = await campaign_repo.update_campaign(campaign_id, update_data)
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    return _campaign_to_response(campaign)


async def update_campaign_general(
    campaign_id: str,
    profile_id: str,
    data: CampaignUpdateRequest,
    *,
    campaign_repo: CampaignRepository | None = None,
    business_repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> CampaignResponse:
    business_id = await _get_business_id_for_user(profile_id, repo=business_repo, member_repo=member_repo)
    campaign_repo = campaign_repo or CampaignRepository()
    campaign = await _ensure_campaign_owner(
        campaign_repo, campaign_id, business_id, profile_id, business_repo=business_repo, member_repo=member_repo,
    )

    # mode="json" is required: bare datetime objects in the payload make the
    # Supabase/httpx client raise (unserializable) → opaque 500 on deadline PATCH.
    update_data: dict[str, Any] = data.model_dump(mode="json", exclude_none=True)
    if not update_data:
        return _campaign_to_response(campaign)

    updated = await campaign_repo.update_campaign(campaign_id, update_data)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    return _campaign_to_response(updated)


async def publish_campaign(
    campaign_id: str,
    profile_id: str,
    *,
    campaign_repo: CampaignRepository | None = None,
    business_repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> CampaignResponse:
    business_id = await _get_business_id_for_user(profile_id, repo=business_repo, member_repo=member_repo)
    campaign_repo = campaign_repo or CampaignRepository()
    campaign = await _ensure_campaign_owner(
        campaign_repo, campaign_id, business_id, profile_id, business_repo=business_repo, member_repo=member_repo,
    )

    required = {
        "title": campaign.title,
        "objective": campaign.objective,
        "description": campaign.description,
        "deliverables": campaign.deliverables,
        "compensation_type": campaign.compensation_type,
        "creator_category": campaign.creator_category,
        "location": campaign.location,
        "max_creators": campaign.max_creators,
        "deadline": campaign.deadline,
    }
    missing = [field for field, value in required.items() if not value]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"missing_fields": missing, "message": "Campaign is incomplete"},
        )

    updated = await campaign_repo.update_campaign(
        campaign_id, {"status": CampaignStatus.ACTIVE.value}
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    return _campaign_to_response(updated)


async def list_campaigns(
    search: str | None,
    category: str | None,
    recommended: bool | None,
    page: int,
    page_size: int,
    user: UserInToken | None = None,
    *,
    location: list[str] | None = None,
    compensation_type: list[str] | None = None,
    budget_ranges: list[str] | None = None,
    budget_min: float | None = None,
    budget_max: float | None = None,
    deliverables: list[str] | None = None,
    only_qualified: bool | None = None,
    campaign_repo: CampaignRepository | None = None,
    creator_repo: CreatorRepository | None = None,
    business_repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> dict:
    campaign_repo = campaign_repo or CampaignRepository()
    business_repo = business_repo or BusinessRepository()

    if recommended and user and user.role.value == "creator":
        creator_repo = creator_repo or CreatorRepository()
        niche = await creator_repo.get_niche_by_profile_id(user.id)
        if niche:
            # Niche is free text (e.g. "Food & Dining"); feed filters on enum values (e.g. "food").
            mapped = _niche_to_category(niche)
            if mapped:
                category = mapped

    extra_cats = _category_values_matching_search(search) if search else []

    # "Only campaigns I qualify for" needs the creator's own numbers — the repo
    # can't reach them, so they're resolved here and passed down as filters.
    creator_follower_count = None
    creator_engagement_rate = None
    if only_qualified and user and user.role.value == "creator":
        creator_repo = creator_repo or CreatorRepository()
        creator = await creator_repo.get_by_profile_id(user.id)
        if creator:
            creator_follower_count = creator.follower_count
            creator_engagement_rate = creator.engagement_rate

    campaigns, total = await campaign_repo.list_active(
        search=search,
        category=category,
        page=page,
        page_size=page_size,
        extra_category_values=extra_cats or None,
        location=location,
        compensation_type=compensation_type,
        budget_ranges=budget_ranges,
        budget_min=budget_min,
        budget_max=budget_max,
        deliverables=deliverables,
        only_qualified=only_qualified,
        creator_follower_count=creator_follower_count,
        creator_engagement_rate=creator_engagement_rate,
    )

    campaign_ids = [c.id for c in campaigns]
    counts = await campaign_repo.fetch_application_counts(campaign_ids)

    # Update campaigns with counts
    for campaign in campaigns:
        count_data = counts.get(campaign.id)
        if count_data:
            campaign.applicant_count = count_data.get("applicant_count")
            campaign.accepted_count = count_data.get("accepted_count")
            campaign.posted_count = count_data.get("posted_count")

    business_ids = list({c.business_id for c in campaigns if c.business_id})
    businesses = await business_repo.get_by_ids(business_ids)
    biz_map = {b.id: b for b in businesses}

    items = []
    for c in campaigns:
        biz = biz_map.get(c.business_id)
        items.append(
            _campaign_to_summary(
                c,
                business_name=biz.business_name if biz else None,
                business_logo_url=biz.logo_url if biz else None,
                is_verified=biz.is_verified if biz else None,
            )
        )

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_campaign(
    campaign_id: str,
    user: UserInToken | None = None,
    *,
    campaign_repo: CampaignRepository | None = None,
    business_repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> CampaignResponse:
    campaign_repo = campaign_repo or CampaignRepository()
    business_repo = business_repo or BusinessRepository()
    campaign = await campaign_repo.get_by_id(campaign_id)

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    if campaign.status == CampaignStatus.DRAFT:
        if not await _can_view_draft_campaign(campaign, user, business_repo=business_repo, member_repo=member_repo):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found",
            )

    counts = await campaign_repo.fetch_application_counts([campaign_id])
    count_data = counts.get(campaign_id)
    if count_data:
        campaign.applicant_count = count_data.get("applicant_count")
        campaign.accepted_count = count_data.get("accepted_count")
        campaign.posted_count = count_data.get("posted_count")

    return _campaign_to_response(campaign)


async def delete_campaign(
    campaign_id: str,
    profile_id: str,
    *,
    campaign_repo: CampaignRepository | None = None,
    business_repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> dict:
    business_id = await _get_business_id_for_user(profile_id, repo=business_repo, member_repo=member_repo)
    campaign_repo = campaign_repo or CampaignRepository()
    await _ensure_campaign_owner(
        campaign_repo, campaign_id, business_id, profile_id, business_repo=business_repo, member_repo=member_repo,
    )

    await campaign_repo.delete_campaign(campaign_id)
    return {"message": "Campaign deleted"}


CAMPAIGN_CATEGORIES: list[CampaignCategoryResponse] = [
    CampaignCategoryResponse(value="food", label="Food & Dining"),
    CampaignCategoryResponse(value="fashion", label="Fashion & Beauty"),
    CampaignCategoryResponse(value="tech", label="Technology"),
    CampaignCategoryResponse(value="travel", label="Travel & Tourism"),
    CampaignCategoryResponse(value="fitness", label="Fitness & Health"),
    CampaignCategoryResponse(value="lifestyle", label="Lifestyle"),
    CampaignCategoryResponse(value="entertainment", label="Entertainment"),
    CampaignCategoryResponse(value="education", label="Education"),
    CampaignCategoryResponse(value="real_estate", label="Real Estate"),
    CampaignCategoryResponse(value="automotive", label="Automotive"),
    CampaignCategoryResponse(value="finance", label="Finance"),
    CampaignCategoryResponse(value="other", label="Other"),
]


async def get_campaign_categories() -> list[CampaignCategoryResponse]:
    return CAMPAIGN_CATEGORIES


async def list_campaign_applications(
    campaign_id: str,
    profile_id: str,
    page: int = 1,
    page_size: int = 20,
    *,
    campaign_repo: CampaignRepository | None = None,
    business_repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
    app_repo: ApplicationRepository | None = None,
) -> dict:
    business_id = await _get_business_id_for_user(profile_id, repo=business_repo, member_repo=member_repo)
    campaign_repo = campaign_repo or CampaignRepository()
    await _ensure_campaign_owner(
        campaign_repo, campaign_id, business_id, profile_id,
        require_write=False, business_repo=business_repo, member_repo=member_repo,
    )

    app_repo = app_repo or ApplicationRepository()
    applications, total = await app_repo.list_by_campaign(
        campaign_id, page=page, page_size=page_size
    )

    items: list[ApplicationWithCreator] = []
    for app in applications:
        creator_data = app.creator or {}
        creator = CreatorSummary(
            id=creator_data.get("id", ""),
            name=creator_data.get("name", ""),
            profile_photo_url=creator_data.get("profile_photo_url"),
            follower_count=creator_data.get("follower_count"),
            niche=creator_data.get("niche"),
        )
        items.append(
            ApplicationWithCreator(
                id=app.id,
                campaign_id=app.campaign_id,
                creator_id=app.creator_id,
                direction=app.direction,
                message=app.message,
                instagram_handle=app.instagram_handle,
                example_content_url=app.example_content_url,
                status=app.status,
                revision_reason=app.revision_reason,
                created_at=app.created_at,
                creator=creator,
            )
        )

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def close_campaign(
    campaign_id: str,
    profile_id: str,
    *,
    campaign_repo: CampaignRepository | None = None,
    business_repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> CampaignResponse:
    """Transition an active campaign to closed — stops new applications/invites."""
    business_id = await _get_business_id_for_user(profile_id, repo=business_repo, member_repo=member_repo)
    campaign_repo = campaign_repo or CampaignRepository()
    campaign = await _ensure_campaign_owner(
        campaign_repo, campaign_id, business_id, profile_id, business_repo=business_repo, member_repo=member_repo,
    )

    if campaign.status != CampaignStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only active campaigns can be closed",
        )

    updated = await campaign_repo.update_campaign(
        campaign_id, {"status": CampaignStatus.CLOSED.value}
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )
    return _campaign_to_response(updated)


async def complete_campaign(
    campaign_id: str,
    profile_id: str,
    *,
    campaign_repo: CampaignRepository | None = None,
    business_repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> CampaignResponse:
    """Mark a campaign as completed (from active or closed)."""
    business_id = await _get_business_id_for_user(profile_id, repo=business_repo, member_repo=member_repo)
    campaign_repo = campaign_repo or CampaignRepository()
    campaign = await _ensure_campaign_owner(
        campaign_repo, campaign_id, business_id, profile_id, business_repo=business_repo, member_repo=member_repo,
    )

    if campaign.status not in (CampaignStatus.ACTIVE, CampaignStatus.CLOSED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only active or closed campaigns can be completed",
        )

    updated = await campaign_repo.update_campaign(
        campaign_id, {"status": CampaignStatus.COMPLETED.value}
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )
    return _campaign_to_response(updated)


async def get_campaign_analytics(
    campaign_id: str,
    profile_id: str,
    *,
    campaign_repo: CampaignRepository | None = None,
    business_repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
    application_repo: ApplicationRepository | None = None,
    collaboration_repo: CollaborationRepository | None = None,
    invoice_repo: InvoiceRepository | None = None,
) -> CampaignAnalyticsResponse:
    business_id = await _get_business_id_for_user(profile_id, repo=business_repo, member_repo=member_repo)
    campaign_repo = campaign_repo or CampaignRepository()
    await _ensure_campaign_owner(
        campaign_repo, campaign_id, business_id, profile_id,
        require_write=False, business_repo=business_repo, member_repo=member_repo,
    )

    application_repo = application_repo or ApplicationRepository()
    collaboration_repo = collaboration_repo or CollaborationRepository()
    invoice_repo = invoice_repo or InvoiceRepository()

    # page_size covers realistic applicant volumes today; total (from the
    # paginated tuple) stays accurate even past that cap, only the status
    # breakdown below would under-count in an unrealistically large campaign.
    applications, applied_count = await application_repo.list_by_campaign(
        campaign_id, page=1, page_size=500
    )
    accepted_count = sum(1 for a in applications if a.status == ApplicationStatus.ACCEPTED)
    rejected_count = sum(1 for a in applications if a.status == ApplicationStatus.REJECTED)
    decided = accepted_count + rejected_count
    response_rate = round(decided / applied_count * 100, 1) if applied_count else None
    acceptance_rate = round(accepted_count / decided * 100, 1) if decided else None

    # page_size covers realistic per-campaign collaboration volumes today.
    collaborations, _ = await collaboration_repo.list_by_campaign(campaign_id, page=1, page_size=500)
    creators_engaged = len({c.creator_id for c in collaborations})

    collab_ids = [c.id for c in collaborations]
    invoices = await invoice_repo.list_by_collaboration_ids(collab_ids)
    invoiced_amount = sum(i.total_amount for i in invoices)
    paid_amount = sum(i.total_amount for i in invoices if i.status == InvoiceStatus.PAID)
    cost_per_creator = round(invoiced_amount / creators_engaged, 2) if creators_engaged else None

    content_metrics_available = False
    for collab_id in collab_ids:
        if await collaboration_repo.list_submissions(collab_id):
            content_metrics_available = True
            break

    return CampaignAnalyticsResponse(
        applied_count=applied_count,
        accepted_count=accepted_count,
        rejected_count=rejected_count,
        response_rate=response_rate,
        acceptance_rate=acceptance_rate,
        creators_engaged=creators_engaged,
        invoiced_amount=invoiced_amount,
        paid_amount=paid_amount,
        cost_per_creator=cost_per_creator,
        content_metrics_available=content_metrics_available,
    )


async def invite_creator(
    campaign_id: str,
    profile_id: str,
    creator_id: str,
    message: str | None,
    *,
    campaign_repo: CampaignRepository | None = None,
    business_repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
    creator_repo: CreatorRepository | None = None,
    app_repo: ApplicationRepository | None = None,
) -> ApplicationResponse:
    business_id = await _get_business_id_for_user(profile_id, repo=business_repo, member_repo=member_repo)
    campaign_repo = campaign_repo or CampaignRepository()
    campaign = await _ensure_campaign_owner(
        campaign_repo, campaign_id, business_id, profile_id, business_repo=business_repo, member_repo=member_repo,
    )

    if campaign.status != CampaignStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This campaign is not open for invites",
        )

    creator_repo = creator_repo or CreatorRepository()
    creator = await creator_repo.get_by_id(creator_id)
    if not creator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator not found",
        )

    app_repo = app_repo or ApplicationRepository()
    existing = await app_repo.get_existing(campaign_id, creator_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Creator already has an application for this campaign",
        )

    insert_data = {
        "campaign_id": campaign_id,
        "creator_id": creator_id,
        "direction": ApplicationDirection.BUSINESS_INVITED.value,
        "message": message,
        "status": ApplicationStatus.PENDING.value,
    }

    application = await app_repo.insert_application(insert_data)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create invite",
        )

    await notification_service.create_notification(
        profile_id=creator.profile_id,
        type=NotificationType.CAMPAIGN_INVITE_RECEIVED,
        title="You've been invited!",
        body=f'A business invited you to apply for "{campaign.title}".',
        related_id=application.id,
    )

    return ApplicationResponse(
        id=application.id,
        campaign_id=application.campaign_id,
        creator_id=application.creator_id,
        direction=application.direction,
        message=application.message,
        instagram_handle=application.instagram_handle,
        example_content_url=application.example_content_url,
        status=application.status,
        revision_reason=application.revision_reason,
        created_at=application.created_at,
    )

async def get_locations(
    *,
    campaign_repo: CampaignRepository | None = None,
) -> dict:
    """Get all unique locations from active campaigns."""
    campaign_repo = campaign_repo or CampaignRepository()
    locations = await campaign_repo.get_locations()
    return {
        "items": locations,
        "total": len(locations),
        "page": 1,
        "page_size": len(locations),
    }


# Fallback span shown only when there isn't a single active cash campaign to
# measure yet (e.g. a brand-new environment) — the slider still needs *some*
# range to render.
_DEFAULT_BUDGET_MIN = 0.0
_DEFAULT_BUDGET_MAX = 100_000.0


async def get_budget_bounds(
    *,
    campaign_repo: CampaignRepository | None = None,
) -> BudgetBoundsResponse:
    """Real min/max cash budget across active campaigns, for sizing the
    filter-sheet slider to actual data instead of a guessed range."""
    campaign_repo = campaign_repo or CampaignRepository()
    bounds = await campaign_repo.get_budget_bounds()
    min_budget = bounds.get("min")
    max_budget = bounds.get("max")
    if min_budget is None or max_budget is None:
        return BudgetBoundsResponse(min_budget=_DEFAULT_BUDGET_MIN, max_budget=_DEFAULT_BUDGET_MAX)
    if min_budget > max_budget:
        min_budget, max_budget = max_budget, min_budget
    return BudgetBoundsResponse(min_budget=min_budget, max_budget=max_budget)
