"""
Business routes — profile, discovery, dashboard.
"""

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_current_user, require_role
from app.core.enums import CampaignStatus, UserRole
from app.schemas.application import ApplicationWithCreator
from app.schemas.business import (
    BusinessResponse,
    BusinessStatsResponse,
    BusinessUpdateRequest,
    CreatorActivityBannerResponse,
    KybReviewRequest,
    KybStatusResponse,
    KybSubmitRequest,
    TeamInviteRequest,
    TeamMemberResponse,
    TeamRoleUpdateRequest,
)
from app.schemas.campaign import CampaignSummary
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.user import UserInToken
from app.services import application_service, business_service

router = APIRouter()


@router.get("/", response_model=PaginatedResponse[BusinessResponse])
async def list_businesses(
    search: str | None = Query(None),
    category: str | None = Query(None),
    city: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List and filter businesses."""
    return await business_service.list_businesses(
        search=search,
        category=category,
        city=city,
        page=page,
        page_size=page_size,
    )


@router.get("/me/stats", response_model=BusinessStatsResponse)
async def get_business_stats(
    user: UserInToken = Depends(get_current_user),
):
    """Get stats for the current business."""
    return await business_service.get_business_stats(profile_id=user.id)


@router.get("/me/creator-activity", response_model=CreatorActivityBannerResponse)
async def get_creator_activity(
    user: UserInToken = Depends(get_current_user),
):
    """'N creators near you posted recently' home-dashboard banner."""
    return await business_service.get_creator_activity_banner(profile_id=user.id)


@router.get("/me/campaigns", response_model=PaginatedResponse[CampaignSummary])
async def list_my_campaigns(
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: UserInToken = Depends(get_current_user),
):
    """List campaigns for the current business."""
    return await business_service.list_my_campaigns(
        profile_id=user.id,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.get("/me/applications", response_model=PaginatedResponse[ApplicationWithCreator])
async def list_my_applications(
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: UserInToken = Depends(get_current_user),
):
    """List applications for the current business."""
    return await application_service.list_business_applications(
        profile_id=user.id,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.get("/me/verification", response_model=KybStatusResponse)
async def get_verification_status(
    user: UserInToken = Depends(get_current_user),
):
    """Get KYB verification status for the current business."""
    return await business_service.get_kyb_status(profile_id=user.id)


@router.post("/me/verification", response_model=KybStatusResponse)
async def submit_verification(
    data: KybSubmitRequest,
    user: UserInToken = Depends(get_current_user),
):
    """Submit business type, legal entity, PAN/GST, and proof document for KYB verification."""
    return await business_service.submit_kyb_verification(profile_id=user.id, data=data)


@router.get(
    "/me/team",
    response_model=list[TeamMemberResponse],
    dependencies=[Depends(require_role(UserRole.BUSINESS, UserRole.SUPERADMIN))],
)
async def list_team_members(
    user: UserInToken = Depends(get_current_user),
):
    """List the current business's team (owner + invited members)."""
    return await business_service.list_team_members(profile_id=user.id)


@router.post(
    "/me/team/invite",
    response_model=TeamMemberResponse,
    dependencies=[Depends(require_role(UserRole.BUSINESS, UserRole.SUPERADMIN))],
)
async def invite_team_member(
    data: TeamInviteRequest,
    user: UserInToken = Depends(get_current_user),
):
    """Invite a teammate by email (owner only) — sends a Supabase invite email."""
    return await business_service.invite_team_member(profile_id=user.id, data=data)


@router.delete(
    "/me/team/{member_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_role(UserRole.BUSINESS, UserRole.SUPERADMIN))],
)
async def remove_team_member(
    member_id: str,
    user: UserInToken = Depends(get_current_user),
):
    """Remove a team member (owner only)."""
    return await business_service.remove_team_member(profile_id=user.id, member_id=member_id)


@router.patch(
    "/me/team/{member_id}",
    response_model=TeamMemberResponse,
    dependencies=[Depends(require_role(UserRole.BUSINESS, UserRole.SUPERADMIN))],
)
async def update_team_member_role(
    member_id: str,
    data: TeamRoleUpdateRequest,
    user: UserInToken = Depends(get_current_user),
):
    """Change a team member's role (owner only)."""
    return await business_service.update_team_member_role(profile_id=user.id, member_id=member_id, data=data)


@router.post(
    "/join",
    response_model=TeamMemberResponse,
    dependencies=[Depends(require_role(UserRole.BUSINESS, UserRole.SUPERADMIN))],
)
async def join_business(
    user: UserInToken = Depends(get_current_user),
):
    """Link the caller's (newly-invited) profile to the pending team invite
    matching their email — called once, right after they set a password via
    Supabase's invite-email link (see POST /auth/reset-password)."""
    return await business_service.join_business(profile_id=user.id, email=user.email)


@router.patch(
    "/{business_id}/verification/review",
    response_model=KybStatusResponse,
    dependencies=[Depends(require_role(UserRole.SUPERADMIN))],
)
async def review_verification(
    business_id: str,
    data: KybReviewRequest,
):
    """Admin approve/reject a pending KYB submission — the only API path off 'pending'."""
    return await business_service.review_kyb_verification(
        business_id=business_id,
        decision=data.decision,
        rejection_reason=data.rejection_reason,
    )


@router.get("/{business_id}", response_model=BusinessResponse)
async def get_business(business_id: str) -> BusinessResponse:
    """Get a specific business's public profile."""
    business = await business_service.get_business_by_id(business_id)
    if not business:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")
    return business


@router.patch(
    "/{business_id}",
    response_model=BusinessResponse,
    dependencies=[Depends(require_role(UserRole.BUSINESS, UserRole.SUPERADMIN))],
)
async def update_business(
    business_id: str,
    data: BusinessUpdateRequest,
    user: UserInToken = Depends(get_current_user),
):
    """Update a business's profile/settings (owner or superadmin only)."""
    return await business_service.update_business(
        business_id=business_id,
        profile_id=user.id,
        role=user.role,
        data=data,
    )


@router.get("/{business_id}/campaigns", response_model=PaginatedResponse[CampaignSummary])
async def list_business_campaigns(
    business_id: str,
    status: str | None = Query(CampaignStatus.ACTIVE.value),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List public campaigns for a business (defaults to active only)."""
    return await business_service.list_business_campaigns(
        business_id=business_id,
        status=status,
        page=page,
        page_size=page_size,
    )
