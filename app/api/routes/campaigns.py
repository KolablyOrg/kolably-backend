"""
Campaign routes — CRUD, 4-step create/publish flow, feed, categories, and invite.
"""

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_current_user, get_optional_user, require_role
from app.core.enums import UserRole
from app.schemas.application import ApplicationResponse, ApplicationWithCreator
from app.schemas.campaign import (
    CampaignCategoryResponse,
    CampaignCreateRequest,
    CampaignDeliverablesRequest,
    CampaignResponse,
    CampaignSummary,
    CampaignTargetingRequest,
    CampaignUpdateRequest,
    InviteRequest,
)
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.user import UserInToken
from app.services import campaign_service

router = APIRouter()


# ── Step 1: Create Draft ──────────────────────────────

@router.post(
    "/",
    response_model=CampaignResponse,
    dependencies=[Depends(require_role(UserRole.BUSINESS, UserRole.SUPERADMIN))],
)
async def create_campaign(
    data: CampaignCreateRequest,
    user: UserInToken = Depends(get_current_user),
):
    """Step 1 — create a new draft campaign."""
    return await campaign_service.create_campaign_step1(user.id, data)


# ── Step 2: Deliverables & Offer ──────────────────────

@router.patch(
    "/{campaign_id}/deliverables",
    response_model=CampaignResponse,
    dependencies=[Depends(require_role(UserRole.BUSINESS, UserRole.SUPERADMIN))],
)
async def update_campaign_deliverables(
    campaign_id: str,
    data: CampaignDeliverablesRequest,
    user: UserInToken = Depends(get_current_user),
):
    """Step 2 — set deliverables and compensation."""
    return await campaign_service.update_campaign_deliverables(campaign_id, user.id, data)


# ── Step 3: Targeting ─────────────────────────────────

@router.patch(
    "/{campaign_id}/targeting",
    response_model=CampaignResponse,
    dependencies=[Depends(require_role(UserRole.BUSINESS, UserRole.SUPERADMIN))],
)
async def update_campaign_targeting(
    campaign_id: str,
    data: CampaignTargetingRequest,
    user: UserInToken = Depends(get_current_user),
):
    """Step 3 — set creator targeting criteria."""
    return await campaign_service.update_campaign_targeting(campaign_id, user.id, data)


# ── Step 4: Finalise & Publish ────────────────────────

@router.patch(
    "/{campaign_id}",
    response_model=CampaignResponse,
    dependencies=[Depends(require_role(UserRole.BUSINESS, UserRole.SUPERADMIN))],
)
async def update_campaign(
    campaign_id: str,
    data: CampaignUpdateRequest,
    user: UserInToken = Depends(get_current_user),
):
    """Step 4 — update cover image, deadline, or any other field."""
    return await campaign_service.update_campaign_general(campaign_id, user.id, data)


@router.post(
    "/{campaign_id}/publish",
    response_model=CampaignResponse,
    dependencies=[Depends(require_role(UserRole.BUSINESS, UserRole.SUPERADMIN))],
)
async def publish_campaign(
    campaign_id: str,
    user: UserInToken = Depends(get_current_user),
):
    """Publish a campaign — flips status to active after validation."""
    return await campaign_service.publish_campaign(campaign_id, user.id)


@router.patch(
    "/{campaign_id}/close",
    response_model=CampaignResponse,
    dependencies=[Depends(require_role(UserRole.BUSINESS, UserRole.SUPERADMIN))],
)
async def close_campaign(
    campaign_id: str,
    user: UserInToken = Depends(get_current_user),
):
    """Close an active campaign — stops new applications and invites."""
    return await campaign_service.close_campaign(campaign_id, user.id)


@router.patch(
    "/{campaign_id}/complete",
    response_model=CampaignResponse,
    dependencies=[Depends(require_role(UserRole.BUSINESS, UserRole.SUPERADMIN))],
)
async def complete_campaign(
    campaign_id: str,
    user: UserInToken = Depends(get_current_user),
):
    """Mark a campaign as completed (from active or closed)."""
    return await campaign_service.complete_campaign(campaign_id, user.id)


# ── Feed & Discovery ──────────────────────────────────

@router.get("/", response_model=PaginatedResponse[CampaignSummary])
async def list_campaigns(
    search: str | None = Query(None),
    category: str | None = Query(None),
    recommended: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: UserInToken = Depends(get_current_user),
):
    """List active campaigns — the main feed for creators."""
    return await campaign_service.list_campaigns(
        search=search,
        category=category,
        recommended=recommended,
        page=page,
        page_size=page_size,
        user=user,
    )


@router.get("/categories", response_model=list[CampaignCategoryResponse])
async def get_campaign_categories():
    """Static list of campaign categories."""
    return await campaign_service.get_campaign_categories()


# ── Detail & General CRUD ─────────────────────────────

@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: str,
    user: UserInToken | None = Depends(get_optional_user),
):
    """Get full campaign details. Draft campaigns are visible only to the owner."""
    return await campaign_service.get_campaign(campaign_id, user=user)


@router.delete(
    "/{campaign_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_role(UserRole.BUSINESS, UserRole.SUPERADMIN))],
)
async def delete_campaign(
    campaign_id: str,
    user: UserInToken = Depends(get_current_user),
):
    """Delete a campaign (owner only)."""
    return await campaign_service.delete_campaign(campaign_id, user.id)


# ── Nested: Applications & Invite ─────────────────────

@router.get(
    "/{campaign_id}/applications",
    response_model=PaginatedResponse[ApplicationWithCreator],
    dependencies=[Depends(require_role(UserRole.BUSINESS, UserRole.SUPERADMIN))],
)
async def list_campaign_applications(
    campaign_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: UserInToken = Depends(get_current_user),
):
    """List applications for a campaign (business owner only)."""
    return await campaign_service.list_campaign_applications(
        campaign_id, user.id, page=page, page_size=page_size
    )


@router.post(
    "/{campaign_id}/invite",
    response_model=ApplicationResponse,
    dependencies=[Depends(require_role(UserRole.BUSINESS, UserRole.SUPERADMIN))],
)
async def invite_creator(
    campaign_id: str,
    data: InviteRequest,
    user: UserInToken = Depends(get_current_user),
):
    """Invite a creator to apply to this campaign."""
    return await campaign_service.invite_creator(
        campaign_id=campaign_id,
        profile_id=user.id,
        creator_id=data.creator_id,
        message=data.message,
    )
