import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from supabase_auth.errors import AuthApiError

from app.core.config import settings
from app.core.crypto import encrypt_token
from app.core.enums import UserRole
from app.core.supabase import get_supabase_admin_client
from app.models.business import Business
from app.repositories.business_member_repo import BusinessMemberRepository
from app.repositories.business_repo import BusinessRepository
from app.repositories.campaign_repo import CampaignRepository
from app.repositories.creator_repo import CreatorRepository
from app.repositories.profile_repo import ProfileRepository
from app.repositories.shortlist_repo import ShortlistRepository
from app.schemas.business import (
    DEFAULT_BUSINESS_NOTIFICATION_PREFERENCES,
    BusinessResponse,
    BusinessStatsResponse,
    BusinessUpdateRequest,
    CreatorActivityBannerResponse,
    ShortlistItemResponse,
    ShortlistUpdateRequest,
    TeamInviteRequest,
    TeamMemberResponse,
    TeamRoleUpdateRequest,
)
from app.schemas.campaign import CampaignSummary
from app.services import business_access, email_service

logger = logging.getLogger(__name__)


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
        instagram_handle=business.instagram_handle,
        website=business.website,
        created_at=business.created_at,
        is_verified=business.is_verified,
        kyb_status=business.kyb_status,
        is_discoverable=business.is_discoverable,
        notification_preferences=business.notification_preferences or DEFAULT_BUSINESS_NOTIFICATION_PREFERENCES,
    )


async def _ensure_business_access(
    business: Business | None,
    profile_id: str,
    role: UserRole,
    *,
    require_write: bool = True,
    member_repo: BusinessMemberRepository | None = None,
) -> Business:
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")
    if role == UserRole.SUPERADMIN or business.profile_id == profile_id:
        return business

    member_repo = member_repo or BusinessMemberRepository()
    member = await member_repo.get_active_membership(business.id, profile_id)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this business profile",
        )
    if require_write and member.role not in business_access.WRITE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers can't make changes — ask an owner or editor on this account.",
        )
    return business


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
        accepted_count=campaign.accepted_count,
        pending_applicant_count=getattr(campaign, "pending_applicant_count", None),
        max_creators=campaign.max_creators,
    )


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
    campaign_repo: CampaignRepository | None = None,
) -> dict:
    repo = repo or BusinessRepository()
    campaign_repo = campaign_repo or CampaignRepository()
    campaigns, total = await repo.list_campaigns(
        business_id=business_id,
        status=status,
        page=page,
        page_size=page_size,
    )

    if campaigns:
        counts = await campaign_repo.fetch_application_counts([c.id for c in campaigns])
        for campaign in campaigns:
            count_data = counts.get(campaign.id)
            if count_data:
                campaign.applicant_count = count_data.get("applicant_count")
                campaign.accepted_count = count_data.get("accepted_count")
                campaign.posted_count = count_data.get("posted_count")
                campaign.pending_applicant_count = count_data.get("pending_applicant_count")

    return {
        "items": [_campaign_to_summary(c) for c in campaigns],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def update_business(
    business_id: str,
    profile_id: str,
    role: UserRole,
    data: BusinessUpdateRequest,
    *,
    repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> BusinessResponse:
    repo = repo or BusinessRepository()
    business = await repo.get_by_id(business_id)
    await _ensure_business_access(business, profile_id, role, member_repo=member_repo)

    update_data = data.model_dump(exclude_none=True)

    if "notification_preferences" in update_data and business.notification_preferences:
        merged = dict(business.notification_preferences)
        merged.update(update_data["notification_preferences"])
        update_data["notification_preferences"] = merged

    if not update_data:
        return _business_to_response(business)

    updated = await repo.update_business(business.id, update_data)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")
    return _business_to_response(updated)


async def list_my_campaigns(
    profile_id: str,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
    *,
    repo: BusinessRepository | None = None,
    campaign_repo: CampaignRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> dict:
    """Campaigns belonging to the caller's own business."""
    repo = repo or BusinessRepository()
    business_id = await _get_business_id_for_user(profile_id, repo=repo, member_repo=member_repo)
    return await list_business_campaigns(
        business_id=business_id,
        status=status,
        page=page,
        page_size=page_size,
        repo=repo,
        campaign_repo=campaign_repo,
    )


async def list_shortlist(
    profile_id: str,
    *,
    repo: BusinessRepository | None = None,
    shortlist_repo: ShortlistRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> list[ShortlistItemResponse]:
    business_id = await _get_business_id_for_user(profile_id, repo=repo, member_repo=member_repo)
    shortlist_repo = shortlist_repo or ShortlistRepository()
    rows = await shortlist_repo.list_by_business(business_id)
    return [ShortlistItemResponse.model_validate(row) for row in rows]


async def update_shortlist(
    profile_id: str,
    creator_id: str,
    data: ShortlistUpdateRequest,
    *,
    repo: BusinessRepository | None = None,
    shortlist_repo: ShortlistRepository | None = None,
    creator_repo: CreatorRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> ShortlistItemResponse:
    business_id = await _get_business_id_for_user(profile_id, repo=repo, member_repo=member_repo)
    creator_repo = creator_repo or CreatorRepository()
    if not await creator_repo.get_by_id(creator_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator not found")
    shortlist_repo = shortlist_repo or ShortlistRepository()
    row = await shortlist_repo.upsert(
        {
            "business_id": business_id,
            "creator_id": creator_id,
            "tags": [tag.strip() for tag in data.tags if tag.strip()][:10],
            "note": data.note.strip() if data.note and data.note.strip() else None,
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    if not row:
        logger.error(
            "shortlist upsert returned no row for business_id=%s creator_id=%s",
            business_id,
            creator_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Something went wrong saving this shortlist entry. Please try again.",
        )
    creator = await creator_repo.get_by_id(creator_id)
    row["creator"] = {
        "id": creator.id,
        "name": creator.name,
        "profile_photo_url": creator.profile_photo_url,
        "follower_count": creator.follower_count,
        "niche": creator.niche,
        "city": creator.city,
        "engagement_rate": creator.engagement_rate,
    }
    return ShortlistItemResponse.model_validate(row)


async def remove_from_shortlist(
    profile_id: str,
    creator_id: str,
    *,
    repo: BusinessRepository | None = None,
    shortlist_repo: ShortlistRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> None:
    business_id = await _get_business_id_for_user(profile_id, repo=repo, member_repo=member_repo)
    shortlist_repo = shortlist_repo or ShortlistRepository()
    await shortlist_repo.delete_for_creator(business_id, creator_id)


async def get_business_stats(
    profile_id: str,
    *,
    repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> BusinessStatsResponse:
    repo = repo or BusinessRepository()
    business_id = await business_access.get_business_id_for_profile(
        profile_id, business_repo=repo, member_repo=member_repo
    )

    if not business_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found",
        )

    campaign_ids = await repo.get_campaign_ids(business_id)
    creators_worked_with_count = await repo.count_distinct_creators(business_id)

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
        campaigns_posted_count=len(campaign_ids),
        creators_worked_with_count=creators_worked_with_count,
    )


async def get_creator_activity_banner(
    profile_id: str,
    *,
    repo: BusinessRepository | None = None,
    creator_repo: CreatorRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> CreatorActivityBannerResponse:
    """'N creators near you posted recently' home-dashboard banner.

    Deliberately city-only, not category-filtered: business.category holds
    free-text industry labels (e.g. "Automotive Dealership", "Fashion Retail")
    that don't share a vocabulary with creator.niche (e.g. "Fashion", "food"),
    so a naive match would almost always return zero for reasons unrelated to
    actual creator activity.
    """
    repo = repo or BusinessRepository()
    creator_repo = creator_repo or CreatorRepository()
    business = await business_access.get_business_for_profile(profile_id, business_repo=repo, member_repo=member_repo)

    if not business or not business.city:
        return CreatorActivityBannerResponse(count=0)

    since_iso = (datetime.now(UTC) - timedelta(days=7)).isoformat()
    active_creators = await creator_repo.list_recently_active_by_city(city=business.city, since_iso=since_iso)
    count = len(active_creators)
    if count == 0:
        return CreatorActivityBannerResponse(count=0, city=business.city)

    avg_followers = round(sum(c.get("follower_count") or 0 for c in active_creators) / count)
    avg_engagement = round(sum(c.get("engagement_rate") or 0 for c in active_creators) / count, 1)

    return CreatorActivityBannerResponse(
        count=count,
        city=business.city,
        avg_followers=avg_followers,
        avg_engagement_rate=avg_engagement,
    )


# ── KYB (Know-Your-Business) Verification Service Methods ──────────────
async def submit_kyb_verification(
    profile_id: str,
    data: Any,
    *,
    repo: BusinessRepository | None = None,
) -> dict:
    repo = repo or BusinessRepository()
    business = await repo.get_by_profile_id(profile_id)
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found",
        )

    now = datetime.now(UTC)
    update_data = {
        "business_type": data.business_type,
        "legal_entity_name": data.legal_entity_name,
        "pan_number": encrypt_token(data.pan_number.upper().strip()),
        "gst_number": data.gst_number,
        "business_proof_document_url": data.document_url,
        "kyb_status": "pending",
        "kyb_submitted_at": now.isoformat(),
        "kyb_rejection_reason": None,
    }

    updated = await repo.update_by_profile_id(profile_id, update_data)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit KYB verification",
        )

    return {
        "status": updated.kyb_status,
        "submitted_at": updated.kyb_submitted_at,
        "verified_at": updated.kyb_verified_at,
        "rejection_reason": updated.kyb_rejection_reason,
    }


async def get_kyb_status(
    profile_id: str,
    *,
    repo: BusinessRepository | None = None,
) -> dict:
    repo = repo or BusinessRepository()
    business = await repo.get_by_profile_id(profile_id)
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found",
        )

    return {
        "status": business.kyb_status or "unverified",
        "submitted_at": business.kyb_submitted_at,
        "verified_at": business.kyb_verified_at,
        "rejection_reason": business.kyb_rejection_reason,
    }


async def review_kyb_verification(
    business_id: str,
    decision: str,
    rejection_reason: str | None = None,
    *,
    repo: BusinessRepository | None = None,
) -> dict:
    """Admin approve/reject action — the only way kyb_status can leave 'pending'
    today, aside from a direct DB edit."""
    repo = repo or BusinessRepository()
    business = await repo.get_by_id(business_id)
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business not found",
        )

    update_data: dict[str, Any] = {"kyb_status": decision}
    if decision == "verified":
        update_data["kyb_verified_at"] = datetime.now(UTC).isoformat()
        update_data["kyb_rejection_reason"] = None
    else:
        update_data["kyb_rejection_reason"] = rejection_reason

    updated = await repo.update_business(business_id, update_data)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update KYB status",
        )

    # Dispatch branded verification outcome email via Resend
    try:
        profile_repo = ProfileRepository()
        owner_profile = await profile_repo.get_by_id(business.profile_id)
        if owner_profile and owner_profile.email:
            biz_name = updated.business_name or "Your Business"
            if decision == "verified":
                await email_service.send_kyb_approved_email(
                    email=owner_profile.email,
                    business_name=biz_name,
                    dashboard_url="https://kolably.com/dashboard",
                    business_id=business_id,
                    profile_id=business.profile_id,
                )
            else:
                await email_service.send_kyb_rejected_email(
                    email=owner_profile.email,
                    business_name=biz_name,
                    rejection_reason=rejection_reason or "Information submitted could not be verified.",
                    resubmit_url="https://kolably.com/settings/verification",
                    business_id=business_id,
                    profile_id=business.profile_id,
                )
    except Exception:
        logger.exception("Failed to dispatch KYB outcome email for business_id=%s", business_id)

    return {
        "status": updated.kyb_status,
        "submitted_at": updated.kyb_submitted_at,
        "verified_at": updated.kyb_verified_at,
        "rejection_reason": updated.kyb_rejection_reason,
    }


# ── Team members ─────────────────────────────────────────────────────
# Invite/remove/role-change are deliberately owner-only (not editor) — team
# composition is a step above day-to-day operational writes.


def _member_to_response(member) -> TeamMemberResponse:
    return TeamMemberResponse(
        id=member.id,
        role=member.role,
        status=member.status,
        invited_email=member.invited_email,
        profile_id=member.profile_id,
        created_at=member.created_at,
        accepted_at=member.accepted_at,
    )


async def _require_owner(
    business_id: str,
    profile_id: str,
    *,
    business_repo: BusinessRepository,
) -> None:
    business = await business_repo.get_by_id(business_id)
    if not business or business.profile_id != profile_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the account owner can manage team members",
        )


async def list_team_members(
    profile_id: str,
    *,
    business_repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> list[TeamMemberResponse]:
    business_repo = business_repo or BusinessRepository()
    member_repo = member_repo or BusinessMemberRepository()

    business_id = await _get_business_id_for_user(profile_id, repo=business_repo, member_repo=member_repo)
    business = await business_repo.get_by_id(business_id)
    members = await member_repo.list_by_business(business_id)

    owner_entry = TeamMemberResponse(
        id=f"owner-{business.id}",
        role="owner",
        status="active",
        invited_email=business.owner_name or "",
        profile_id=business.profile_id,
        created_at=business.created_at,
        accepted_at=business.created_at,
    )
    return [owner_entry] + [_member_to_response(m) for m in members]


async def invite_team_member(
    profile_id: str,
    data: TeamInviteRequest,
    *,
    business_repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> TeamMemberResponse:
    business_repo = business_repo or BusinessRepository()
    member_repo = member_repo or BusinessMemberRepository()

    business_id = await _get_business_id_for_user(profile_id, repo=business_repo, member_repo=member_repo)
    await _require_owner(business_id, profile_id, business_repo=business_repo)

    existing = await member_repo.get_pending_by_email(business_id, data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email already has a pending invite",
        )

    member = await member_repo.insert_member(
        {
            "business_id": business_id,
            "invited_email": data.email,
            "role": data.role,
            "invited_by": profile_id,
            "status": "pending",
        }
    )
    if not member:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create invite",
        )

    supabase_admin = await get_supabase_admin_client()
    try:
        await supabase_admin.auth.admin.invite_user_by_email(
            data.email,
            {"data": {"role": "business"}, "redirect_to": settings.WEB_TEAM_INVITE_REDIRECT_URL},
        )
    except AuthApiError:
        # Most likely: this email already has a Kolably account. The pending
        # `business_members` row still lets them join — see `join_business` —
        # they just won't get Supabase's invite email prompting them to.
        pass

    # Send branded team invitation email via Resend
    business_record = await business_repo.get_by_id(business_id)
    inviter_name = (business_record.owner_name if business_record else None) or "A team owner"
    biz_name = (business_record.business_name if business_record else None) or "Your Team"
    await email_service.send_team_invitation_email(
        email=data.email,
        inviter_name=inviter_name,
        business_name=biz_name,
        role=data.role,
        accept_url=settings.WEB_TEAM_INVITE_REDIRECT_URL,
        business_id=business_id,
        inviter_profile_id=profile_id,
    )

    return _member_to_response(member)


async def remove_team_member(
    profile_id: str,
    member_id: str,
    *,
    business_repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> dict:
    business_repo = business_repo or BusinessRepository()
    member_repo = member_repo or BusinessMemberRepository()

    member = await member_repo.get_by_id(member_id)
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team member not found")
    await _require_owner(member.business_id, profile_id, business_repo=business_repo)

    await member_repo.update_member(member_id, {"status": "revoked"})
    return {"message": "Team member removed"}


async def update_team_member_role(
    profile_id: str,
    member_id: str,
    data: TeamRoleUpdateRequest,
    *,
    business_repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> TeamMemberResponse:
    business_repo = business_repo or BusinessRepository()
    member_repo = member_repo or BusinessMemberRepository()

    member = await member_repo.get_by_id(member_id)
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team member not found")
    await _require_owner(member.business_id, profile_id, business_repo=business_repo)

    updated = await member_repo.update_member(member_id, {"role": data.role})
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update role",
        )
    return _member_to_response(updated)


async def join_business(
    profile_id: str,
    email: str,
    *,
    member_repo: BusinessMemberRepository | None = None,
) -> TeamMemberResponse:
    """Called once by an invited teammate right after they set their password
    via Supabase's invite link (same POST /auth/reset-password flow used for
    password recovery) — links their brand-new profile to the pending invite
    matching their email."""
    member_repo = member_repo or BusinessMemberRepository()

    pending = await member_repo.get_any_pending_by_email(email)
    if not pending:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pending invite found for this email",
        )

    updated = await member_repo.update_member(
        pending.id,
        {
            "profile_id": profile_id,
            "status": "active",
            "accepted_at": datetime.now(UTC).isoformat(),
        },
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to join business",
        )
    return _member_to_response(updated)
