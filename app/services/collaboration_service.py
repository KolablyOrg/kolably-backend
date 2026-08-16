import logging
from datetime import UTC, datetime

from fastapi import HTTPException, status

from app.core.crypto import decrypt_token
from app.core.enums import (
    CollaborationStatus,
    DraftReviewStatus,
    InvoiceStatus,
    NotificationType,
    SubmissionType,
)
from app.models.business import Business
from app.models.campaign import Campaign
from app.models.collaboration import Collaboration
from app.repositories.business_member_repo import BusinessMemberRepository
from app.repositories.business_repo import BusinessRepository
from app.repositories.campaign_repo import CampaignRepository
from app.repositories.collaboration_repo import CollaborationRepository
from app.repositories.creator_repo import CreatorRepository
from app.repositories.invoice_repo import InvoiceRepository
from app.schemas.collaboration import (
    ApproveSubmissionRequest,
    ContentSubmitRequest,
    RequestRevisionRequest,
)
from app.services import business_access, chat_service, instagram_service, notification_service

logger = logging.getLogger(__name__)


def _required_deliverable_count(campaign: Campaign | None) -> int:
    if not campaign or not campaign.deliverables:
        return 0
    total = 0
    for deliverable in campaign.deliverables:
        quantity = deliverable.quantity if hasattr(deliverable, "quantity") else deliverable.get("quantity", 1)
        try:
            parsed = int(quantity)
        except (TypeError, ValueError):
            parsed = 1
        total += max(1, min(parsed, 20))
    return total


def _latest_drafts_by_index(submissions: list[dict]) -> dict[int, dict]:
    by_index: dict[int, dict] = {}
    unindexed: list[dict] = []
    for sub in submissions:
        if (sub.get("submission_type") or SubmissionType.DRAFT.value) == SubmissionType.LIVE.value:
            continue
        idx = sub.get("deliverable_index")
        if idx is None or not isinstance(idx, (int, float)):
            unindexed.append(sub)
            continue
        key = int(idx)
        existing = by_index.get(key)
        if not existing or sub.get("submitted_at", "") > existing.get("submitted_at", ""):
            by_index[key] = sub

    if by_index:
        return by_index

    if not unindexed:
        return {}

    sorted_subs = sorted(unindexed, key=lambda s: s.get("submitted_at", ""), reverse=True)
    latest_time = sorted_subs[0].get("submitted_at", "")
    batch = [sub for sub in sorted_subs if sub.get("submitted_at", "") == latest_time] or sorted_subs
    if len(batch) > 1:
        from datetime import datetime

        def _ts(value: str) -> float:
            try:
                return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
            except (TypeError, ValueError):
                return 0.0

        anchor = _ts(batch[0].get("submitted_at", ""))
        batch = [sub for sub in batch if anchor - _ts(sub.get("submitted_at", "")) <= 120]

    batch = sorted(batch, key=lambda s: s.get("submitted_at", ""))
    return {index: sub for index, sub in enumerate(batch)}


def _serialize_submission(sub: dict) -> dict:
    return {
        "id": sub["id"],
        "collaboration_id": sub["collaboration_id"],
        "content_url": sub["content_url"],
        "platform": sub["platform"],
        "content_type": sub.get("content_type"),
        "deliverable_index": sub.get("deliverable_index"),
        "submission_type": sub.get("submission_type") or SubmissionType.DRAFT.value,
        "views": sub.get("views"),
        "likes": sub.get("likes"),
        "comments": sub.get("comments"),
        "synced_at": sub.get("synced_at"),
        "submitted_at": sub["submitted_at"],
        "verification_checks": sub.get("verification_checks"),
        "verified_at": sub.get("verified_at"),
        "draft_status": sub.get("draft_status") or DraftReviewStatus.PENDING.value,
        "revision_notes": sub.get("revision_notes") or [],
        "revision_overall_note": sub.get("revision_overall_note"),
    }


async def _all_required_drafts_approved(
    collaboration_id: str,
    *,
    repo: CollaborationRepository,
    campaign_repo: CampaignRepository,
    campaign_id: str,
) -> bool:
    submissions = await repo.list_submissions(collaboration_id)
    by_index = _latest_drafts_by_index(submissions)
    if not by_index:
        return False

    campaign = await campaign_repo.get_by_id(campaign_id)
    required = _required_deliverable_count(campaign)
    if required <= 0:
        required = max(by_index.keys()) + 1

    if len(by_index) < required:
        return False
    for index in range(required):
        sub = by_index.get(index)
        if not sub:
            return False
        if (sub.get("draft_status") or DraftReviewStatus.PENDING.value) != DraftReviewStatus.APPROVED.value:
            return False
    return True


async def _get_owned_draft_submission(
    collaboration_id: str,
    submission_id: str,
    *,
    repo: CollaborationRepository,
) -> dict:
    submissions = await repo.list_submissions(collaboration_id)
    submission = next((sub for sub in submissions if sub["id"] == submission_id), None)
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found",
        )
    if (submission.get("submission_type") or SubmissionType.DRAFT.value) == SubmissionType.LIVE.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only draft submissions can be reviewed",
        )
    return submission


async def _get_creator_id_for_user(
    profile_id: str,
    *,
    repo: CreatorRepository | None = None,
) -> str:
    repo = repo or CreatorRepository()
    creator_id = await repo.get_id_by_profile_id(profile_id)
    if not creator_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator profile not found",
        )
    return creator_id


async def _get_business_id_for_user(
    profile_id: str,
    *,
    repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> str:
    repo = repo or BusinessRepository()
    business_id = await business_access.get_business_id_for_profile(
        profile_id, business_repo=repo, member_repo=member_repo
    )
    if not business_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found",
        )
    return business_id


def _collaboration_to_response(
    collab: Collaboration,
    *,
    campaign: Campaign | None = None,
    business: Business | None = None,
    revision_history: list[dict] | None = None,
) -> dict:
    """Convert a Collaboration model to a response dict.

    campaign/business are optional joins — pass them when available so the
    mobile collab screens (which render brand name/logo/payout/deadline)
    have something to read; omitting them still returns a valid response
    with those fields null.
    """
    resp: dict = {
        "id": collab.id,
        "campaign_id": collab.campaign_id,
        "creator_id": collab.creator_id,
        "business_id": collab.business_id,
        "status": collab.status.value if hasattr(collab.status, "value") else collab.status,
        "content_submissions": [],
        "affiliate_url": collab.deliverables.get("affiliate_url") if isinstance(collab.deliverables, dict) else None,
        "created_at": collab.created_at,
        "completed_at": collab.completed_at,
        "revision_notes": collab.revision_notes or [],
        "revision_overall_note": collab.revision_overall_note,
        "revision_rounds": collab.revision_rounds,
        "revision_limit": 1,
        "revision_history": revision_history or [],
        "payment_confirmed_at": collab.payment_confirmed_at,
        "payment_confirmed_by": collab.payment_confirmed_by,
        "campaign_title": campaign.title if campaign else None,
        "business_name": business.business_name if business else None,
        "brand_logo": business.logo_url if business else None,
        "campaign": None,
        "business": None,
    }
    if campaign:
        resp["campaign"] = {
            "title": campaign.title,
            "deliverables": [d.to_dict() for d in campaign.deliverables],
            "deadline": campaign.deadline,
            "content_due_at": campaign.content_due_at,
            "compensation_type": campaign.compensation_type,
            "cash_amount_min": campaign.cash_amount_min,
            "cash_amount_max": campaign.cash_amount_max,
            "free_product_description": campaign.free_product_description,
        }
    if business:
        resp["business"] = {
            "id": business.id,
            "business_name": business.business_name,
            "logo_url": business.logo_url,
            "gst_number": business.gst_number,
            # profile_id is the profile's id (see business_service's
            # user_id mapping) — the client needs it to open the chat.
            "user_id": business.profile_id,
        }
    return resp


async def _fetch_joins(
    collabs: list[Collaboration],
    *,
    campaign_repo: CampaignRepository,
    business_repo: BusinessRepository,
) -> tuple[dict[str, Campaign], dict[str, Business]]:
    campaign_ids = list({c.campaign_id for c in collabs if c.campaign_id})
    business_ids = list({c.business_id for c in collabs if c.business_id})
    campaigns = await campaign_repo.get_by_ids(campaign_ids)
    businesses = await business_repo.get_by_ids(business_ids)
    return (
        {c.id: c for c in campaigns},
        {b.id: b for b in businesses},
    )


async def list_collaborations(
    profile_id: str,
    role: str,
    page: int = 1,
    page_size: int = 20,
    campaign_id: str | None = None,
    *,
    repo: CollaborationRepository | None = None,
    creator_repo: CreatorRepository | None = None,
    business_repo: BusinessRepository | None = None,
    campaign_repo: CampaignRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> dict:
    repo = repo or CollaborationRepository()
    business_repo = business_repo or BusinessRepository()
    campaign_repo = campaign_repo or CampaignRepository()

    if role == "creator":
        creator_id = await _get_creator_id_for_user(profile_id, repo=creator_repo)
        collabs, total = await repo.list_by_creator(
            creator_id=creator_id,
            page=page,
            page_size=page_size,
            campaign_id=campaign_id,
        )
    elif role == "business":
        business_id = await _get_business_id_for_user(profile_id, repo=business_repo, member_repo=member_repo)
        collabs, total = await repo.list_by_business(
            business_id=business_id,
            page=page,
            page_size=page_size,
            campaign_id=campaign_id,
        )
    else:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    campaign_map, business_map = await _fetch_joins(
        collabs, campaign_repo=campaign_repo, business_repo=business_repo
    )
    items = [
        _collaboration_to_response(
            c,
            campaign=campaign_map.get(c.campaign_id),
            business=business_map.get(c.business_id),
        )
        for c in collabs
    ]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_collaboration(
    collaboration_id: str,
    profile_id: str,
    role: str,
    *,
    repo: CollaborationRepository | None = None,
    campaign_repo: CampaignRepository | None = None,
    business_repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
    creator_repo: CreatorRepository | None = None,
) -> dict:
    repo = repo or CollaborationRepository()
    campaign_repo = campaign_repo or CampaignRepository()
    business_repo = business_repo or BusinessRepository()
    collab = await repo.get_by_id(collaboration_id)

    if not collab:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collaboration not found",
        )

    if role == "creator":
        creator_id = await _get_creator_id_for_user(profile_id, repo=creator_repo)
        if collab.creator_id != creator_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not own this collaboration",
            )
    elif role == "business":
        access_role = await business_access.get_role_for_profile(
            collab.business_id, profile_id, business_repo=business_repo, member_repo=member_repo
        )
        if access_role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not own this collaboration",
            )

    submissions_raw = await repo.list_submissions(collaboration_id)
    revision_history = await repo.list_revision_history(collaboration_id)
    submissions = [
        _serialize_submission(sub)
        for sub in submissions_raw
    ]

    campaign = await campaign_repo.get_by_id(collab.campaign_id)
    business = await business_repo.get_by_id(collab.business_id)
    resp = _collaboration_to_response(collab, campaign=campaign, business=business)
    resp["content_submissions"] = submissions
    resp["revision_history"] = revision_history
    return resp


async def _get_owned_collaboration(
    collaboration_id: str,
    profile_id: str,
    *,
    repo: CollaborationRepository,
    business_repo: BusinessRepository,
    member_repo: BusinessMemberRepository | None = None,
) -> Collaboration:
    """Load a collaboration, ensuring the caller has write access to the
    business side of it (owner or editor — viewers are blocked) — only the
    business manages a collaboration's lifecycle."""
    collab = await repo.get_by_id(collaboration_id)
    if not collab:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collaboration not found",
        )

    business_id = await _get_business_id_for_user(profile_id, repo=business_repo, member_repo=member_repo)
    if collab.business_id != business_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this collaboration",
        )
    await business_access.require_write_access(
        business_id, profile_id, business_repo=business_repo, member_repo=member_repo
    )
    return collab


async def complete_collaboration(
    collaboration_id: str,
    profile_id: str,
    *,
    repo: CollaborationRepository | None = None,
    business_repo: BusinessRepository | None = None,
    creator_repo: CreatorRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> dict:
    repo = repo or CollaborationRepository()
    business_repo = business_repo or BusinessRepository()
    creator_repo = creator_repo or CreatorRepository()

    collab = await _get_owned_collaboration(
        collaboration_id, profile_id, repo=repo, business_repo=business_repo, member_repo=member_repo
    )
    if collab.status == CollaborationStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Collaboration is already completed",
        )
    if collab.status == CollaborationStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot complete a cancelled collaboration",
        )

    updated = await repo.update_status(collaboration_id, {
        "status": CollaborationStatus.COMPLETED.value,
        "completed_at": datetime.now(UTC).isoformat(),
    })
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete collaboration",
        )

    creator = await creator_repo.get_by_id(collab.creator_id)
    if creator:
        await notification_service.create_notification(
            profile_id=creator.profile_id,
            type=NotificationType.COLLABORATION_COMPLETED,
            title="Collaboration completed",
            body="A business marked your collaboration as completed.",
            related_id=collaboration_id,
        )

    return _collaboration_to_response(updated)


async def cancel_collaboration(
    collaboration_id: str,
    profile_id: str,
    *,
    repo: CollaborationRepository | None = None,
    business_repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> dict:
    repo = repo or CollaborationRepository()
    business_repo = business_repo or BusinessRepository()

    collab = await _get_owned_collaboration(
        collaboration_id, profile_id, repo=repo, business_repo=business_repo, member_repo=member_repo
    )
    if collab.status in (CollaborationStatus.COMPLETED, CollaborationStatus.CANCELLED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Collaboration is already {collab.status.value}",
        )

    updated = await repo.update_status(collaboration_id, {
        "status": CollaborationStatus.CANCELLED.value,
    })
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel collaboration",
        )

    return _collaboration_to_response(updated)


async def submit_content(
    collaboration_id: str,
    profile_id: str,
    data: ContentSubmitRequest,
    *,
    repo: CollaborationRepository | None = None,
    creator_repo: CreatorRepository | None = None,
    campaign_repo: CampaignRepository | None = None,
    business_repo: BusinessRepository | None = None,
) -> dict:
    """Creator submits a post/reel link for brand review.

    Covers both phases of the same loop, distinguished by `data.submission_type`:
    - "draft" (default — unchanged from before this covered the live phase
      too): a pre-approval cut, submitted from `active` or
      `revision_requested`. Moves status to `content_submitted`.
    - "live": the actual published post, only accepted once the business has
      approved a draft (`approved` status). Moves status to `live_submitted`
      so the business can verify + confirm payment.

    Does not attempt to auto-fetch view/like/comment counts from Instagram —
    that would require resolving an arbitrary pasted URL to a media id the
    Graph API recognizes (matching against the creator's own media list,
    handling token expiry, etc.), which is real scope beyond making this
    endpoint exist. views/likes/comments are stored only if the caller
    supplies them; they're null otherwise, same as a fresh, unsynced row.
    """
    repo = repo or CollaborationRepository()
    creator_repo = creator_repo or CreatorRepository()
    business_repo = business_repo or BusinessRepository()

    creator_id = await _get_creator_id_for_user(profile_id, repo=creator_repo)
    collab = await repo.get_by_id(collaboration_id)
    if not collab:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collaboration not found",
        )
    if collab.creator_id != creator_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this collaboration",
        )
    if collab.status in (CollaborationStatus.COMPLETED, CollaborationStatus.CANCELLED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot submit content for a {collab.status.value} collaboration",
        )

    submission_type = (
        data.submission_type.value
        if hasattr(data.submission_type, "value")
        else data.submission_type
    ) or SubmissionType.DRAFT.value

    if submission_type == SubmissionType.LIVE.value:
        if collab.status not in (
            CollaborationStatus.APPROVED,
            CollaborationStatus.LIVE_SUBMITTED,
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The draft needs to be approved before you submit the live post link",
            )
        next_status = CollaborationStatus.LIVE_SUBMITTED
    else:
        # Permissive on purpose, same as before this endpoint distinguished
        # draft/live: active, content_submitted (correcting/replacing before
        # review), and revision_requested (resubmitting) are all fine. Only
        # the states past the draft phase (approved/live_submitted) or the
        # collaboration being over don't make sense for a *draft* submission.
        if collab.status in (
            CollaborationStatus.APPROVED,
            CollaborationStatus.LIVE_SUBMITTED,
            CollaborationStatus.COMPLETED,
            CollaborationStatus.CANCELLED,
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot submit a draft for a {collab.status.value} collaboration",
            )
        next_status = CollaborationStatus.CONTENT_SUBMITTED

    platform = data.platform.value if hasattr(data.platform, "value") else data.platform
    await repo.insert_submission({
        "collaboration_id": collaboration_id,
        "content_url": data.content_url,
        "platform": platform,
        # Identifies *which* deliverable this fulfils. Without these the
        # brand just sees N rows that all say "instagram" and can't tell
        # reel 1 from reel 2, or spot what's still missing.
        "content_type": data.content_type,
        "deliverable_index": data.deliverable_index,
        "submission_type": submission_type,
        "draft_status": DraftReviewStatus.PENDING.value
        if submission_type == SubmissionType.DRAFT.value
        else None,
        "views": data.views,
        "likes": data.likes,
        "comments": data.comments,
        "notes": data.notes,
    })

    if collab.status != next_status:
        updated = await repo.update_status(collaboration_id, {"status": next_status.value})
        if updated:
            collab = updated

    business = await business_repo.get_by_id(collab.business_id)
    phase = "live post" if submission_type == SubmissionType.LIVE.value else "draft"
    if business:
        await notification_service.create_notification(
            profile_id=business.profile_id,
            type=NotificationType.COLLABORATION_CONTENT_SUBMITTED,
            title="Content submitted",
            body=f"A creator submitted a {phase} for your collaboration.",
            related_id=collaboration_id,
        )

    await chat_service.post_collaboration_event(
        collaboration_id,
        profile_id,
        "content_submitted",
        f"Submitted a {phase} for review.",
        extra={"submission_type": submission_type, "content_url": data.content_url},
    )

    return await get_collaboration(
        collaboration_id, profile_id, "creator",
        repo=repo, campaign_repo=campaign_repo, business_repo=business_repo, creator_repo=creator_repo,
    )


async def request_revision(
    collaboration_id: str,
    profile_id: str,
    data: RequestRevisionRequest,
    *,
    repo: CollaborationRepository | None = None,
    business_repo: BusinessRepository | None = None,
    creator_repo: CreatorRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> dict:
    """Business asks for changes on one submitted draft deliverable."""
    repo = repo or CollaborationRepository()
    business_repo = business_repo or BusinessRepository()
    creator_repo = creator_repo or CreatorRepository()

    collab = await _get_owned_collaboration(
        collaboration_id, profile_id, repo=repo, business_repo=business_repo, member_repo=member_repo
    )
    if collab.status != CollaborationStatus.CONTENT_SUBMITTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only a submitted draft awaiting review can have a revision requested",
        )
    if collab.revision_rounds >= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The free revision round has already been used for this collaboration",
        )
    if not data.notes and not (data.overall_note and data.overall_note.strip()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Add at least one timestamped note or an overall note",
        )

    submission = await _get_owned_draft_submission(
        collaboration_id, data.submission_id, repo=repo
    )
    if (submission.get("draft_status") or DraftReviewStatus.PENDING.value) == DraftReviewStatus.APPROVED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This deliverable has already been approved",
        )

    updated_submission = await repo.update_submission(
        data.submission_id,
        {
            "draft_status": DraftReviewStatus.NEEDS_REVISION.value,
            "revision_notes": [n.model_dump() for n in data.notes],
            "revision_overall_note": (data.overall_note or "").strip() or None,
        },
    )
    if not updated_submission:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update submission",
        )

    updated = await repo.update_status(collaboration_id, {
        "revision_rounds": collab.revision_rounds + 1,
        "revision_notes": [n.model_dump() for n in data.notes],
        "revision_overall_note": (data.overall_note or "").strip() or None,
    })
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to request revision",
        )

    history = await repo.insert_revision_history({
        "collaboration_id": collaboration_id,
        "revision_number": collab.revision_rounds + 1,
        "requested_by": profile_id,
        "notes": [n.model_dump() for n in data.notes],
        "overall_note": (data.overall_note or "").strip() or None,
    })
    if not history:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record revision history",
        )

    creator = await creator_repo.get_by_id(collab.creator_id)
    if creator:
        await notification_service.create_notification(
            profile_id=creator.profile_id,
            type=NotificationType.REVISION_REQUESTED,
            title="Revision requested",
            body="The business asked for changes on one of your submitted drafts.",
            related_id=collaboration_id,
        )

    overall_note = (data.overall_note or "").strip()
    note_count = len(data.notes or [])
    deliverable_label = submission.get("content_type") or "draft"
    summary = overall_note or (
        f"Requested changes on the {deliverable_label}."
        if note_count == 0
        else f"Requested changes on the {deliverable_label} ({note_count} note{'s' if note_count != 1 else ''})."
    )
    await chat_service.post_collaboration_event(
        collaboration_id,
        profile_id,
        "revision_requested",
        summary,
        extra={
            "submission_id": data.submission_id,
            "deliverable_index": submission.get("deliverable_index"),
            "overall_note": overall_note or None,
            "notes": [n.model_dump() for n in (data.notes or [])],
        },
    )

    return await get_collaboration(
        collaboration_id, profile_id, "business",
        repo=repo, business_repo=business_repo, creator_repo=creator_repo, member_repo=member_repo,
    )


async def approve_draft(
    collaboration_id: str,
    profile_id: str,
    data: ApproveSubmissionRequest,
    *,
    repo: CollaborationRepository | None = None,
    business_repo: BusinessRepository | None = None,
    creator_repo: CreatorRepository | None = None,
    campaign_repo: CampaignRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> dict:
    """Business approves one draft deliverable. When every required deliverable
    is approved, the collaboration moves to `approved`."""
    repo = repo or CollaborationRepository()
    business_repo = business_repo or BusinessRepository()
    creator_repo = creator_repo or CreatorRepository()
    campaign_repo = campaign_repo or CampaignRepository()

    collab = await _get_owned_collaboration(
        collaboration_id, profile_id, repo=repo, business_repo=business_repo, member_repo=member_repo
    )
    if collab.status != CollaborationStatus.CONTENT_SUBMITTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only a submitted draft awaiting review can be approved",
        )

    submission = await _get_owned_draft_submission(
        collaboration_id, data.submission_id, repo=repo
    )
    if (submission.get("draft_status") or DraftReviewStatus.PENDING.value) == DraftReviewStatus.APPROVED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This deliverable has already been approved",
        )

    updated_submission = await repo.update_submission(
        data.submission_id,
        {"draft_status": DraftReviewStatus.APPROVED.value},
    )
    if not updated_submission:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to approve draft",
        )

    deliverable_label = submission.get("content_type") or "draft"
    all_approved = await _all_required_drafts_approved(
        collaboration_id,
        repo=repo,
        campaign_repo=campaign_repo,
        campaign_id=collab.campaign_id,
    )

    updated = collab
    if all_approved:
        updated = await repo.update_status(
            collaboration_id, {"status": CollaborationStatus.APPROVED.value}
        )
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to approve draft",
            )

        creator = await creator_repo.get_by_id(collab.creator_id)
        if creator:
            await notification_service.create_notification(
                profile_id=creator.profile_id,
                type=NotificationType.COLLABORATION_DRAFT_APPROVED,
                title="Draft approved",
                body="All deliverables were approved. You can now publish the live posts.",
                related_id=collaboration_id,
            )

        await chat_service.post_collaboration_event(
            collaboration_id,
            profile_id,
            "draft_approved",
            "Approved all deliverables. Ready to publish.",
        )
    else:
        await chat_service.post_collaboration_event(
            collaboration_id,
            profile_id,
            "draft_approved",
            f"Approved the {deliverable_label}.",
            extra={
                "submission_id": data.submission_id,
                "deliverable_index": submission.get("deliverable_index"),
            },
        )

    return await get_collaboration(
        collaboration_id, profile_id, "business",
        repo=repo, business_repo=business_repo, creator_repo=creator_repo, member_repo=member_repo,
    )


async def verify_live_post(
    collaboration_id: str,
    profile_id: str,
    *,
    repo: CollaborationRepository | None = None,
    business_repo: BusinessRepository | None = None,
    creator_repo: CreatorRepository | None = None,
    campaign_repo: CampaignRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> dict:
    """Best-effort automated check of the creator's live post, for Instagram
    submissions only (the only platform this app has Graph API access for —
    no YouTube/TikTok integration exists, see docs/PRE_LAUNCH_GAP_ANALYSIS.md).

    Checks it can genuinely make from the Graph API:
    - post_live: the submitted permalink matches one of the creator's recent
      media items.
    - tagged_business: the post's caption mentions the business's own
      @instagram_handle.

    What it deliberately does NOT fake: whether the post carries Instagram's
    native "Paid Partnership" label. That isn't a field this API tier
    exposes reliably, so that check is always returned as `null` (not
    checkable — needs the business's own judgment), never a fabricated
    true/false.

    Never raises just because auto-verification wasn't possible (no IG
    token, non-Instagram platform, transient API error) — it degrades to
    "nothing could be auto-checked" so the business can still fall through
    to manual judgment instead of getting stuck on an error screen.
    """
    repo = repo or CollaborationRepository()
    business_repo = business_repo or BusinessRepository()
    creator_repo = creator_repo or CreatorRepository()

    collab = await _get_owned_collaboration(
        collaboration_id, profile_id, repo=repo, business_repo=business_repo, member_repo=member_repo
    )
    if collab.status != CollaborationStatus.LIVE_SUBMITTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No live post submission awaiting verification",
        )

    submission = await repo.get_latest_submission(collaboration_id, SubmissionType.LIVE.value)
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No live post submission found",
        )

    checks: dict[str, bool | None] = {
        "post_live": None,
        "tagged_business": None,
        "paid_partnership_label": None,
    }

    if submission.get("platform") == "instagram":
        creator = await creator_repo.get_by_id(collab.creator_id)
        business = await business_repo.get_by_id(collab.business_id)
        if creator and creator.instagram_access_token:
            try:
                access_token = decrypt_token(creator.instagram_access_token)
                media = await instagram_service.fetch_media(access_token)
                submitted_url = (submission.get("content_url") or "").rstrip("/")
                match = next(
                    (m for m in media if (m.get("permalink") or "").rstrip("/") == submitted_url),
                    None,
                )
                checks["post_live"] = match is not None
                if match and business and business.instagram_handle:
                    handle = business.instagram_handle.lstrip("@").lower()
                    caption = (match.get("caption") or "").lower()
                    checks["tagged_business"] = handle in caption if handle else None
            except Exception:
                logger.exception(
                    "Live-post verification failed for collaboration_id=%s", collaboration_id
                )
                # Leave checks as None ("not checkable") rather than surfacing
                # a 500 — a flaky Graph API call shouldn't block the business
                # from proceeding to a manual decision.

    now = datetime.now(UTC).isoformat()
    updated_submission = await repo.update_submission(submission["id"], {
        "verification_checks": checks,
        "verified_at": now,
    })
    if not updated_submission:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record live-post verification",
        )

    creator = await creator_repo.get_by_id(collab.creator_id)
    if creator:
        await notification_service.create_notification(
            profile_id=creator.profile_id,
            type=NotificationType.COLLABORATION_LIVE_VERIFIED,
            title="Live post verification updated",
            body="Your live post was reviewed. Any unavailable checks still require manual confirmation.",
            related_id=collaboration_id,
        )

    return await get_collaboration(
        collaboration_id, profile_id, "business",
        repo=repo, campaign_repo=campaign_repo, business_repo=business_repo, member_repo=member_repo,
    )


async def confirm_payment(
    collaboration_id: str,
    profile_id: str,
    *,
    repo: CollaborationRepository | None = None,
    business_repo: BusinessRepository | None = None,
    creator_repo: CreatorRepository | None = None,
    invoice_repo: InvoiceRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> dict:
    """Business confirms they paid the creator directly (Kolably never
    moves the money itself — see `BizMarkPaid` in the design and the
    product's consistent "pay directly" framing elsewhere). Completes the
    collaboration in the same step, reusing `complete_collaboration`'s
    notify-creator behavior rather than duplicating it.
    """
    repo = repo or CollaborationRepository()
    business_repo = business_repo or BusinessRepository()
    creator_repo = creator_repo or CreatorRepository()
    invoice_repo = invoice_repo or InvoiceRepository()

    collab = await _get_owned_collaboration(
        collaboration_id, profile_id, repo=repo, business_repo=business_repo, member_repo=member_repo
    )
    if collab.status != CollaborationStatus.LIVE_SUBMITTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirm the live post before marking payment as sent",
        )

    now = datetime.now(UTC).isoformat()
    updated = await repo.update_status(collaboration_id, {
        "payment_confirmed_at": now,
        "payment_confirmed_by": profile_id,
        "status": CollaborationStatus.COMPLETED.value,
        "completed_at": now,
    })
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to confirm payment",
        )

    invoice = await invoice_repo.get_by_collaboration_id(collaboration_id)
    if invoice and not await invoice_repo.update_status(
        invoice.id,
        {"status": InvoiceStatus.PAID.value, "paid_at": now, "paid_by": profile_id},
    ):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Payment confirmed but invoice synchronization failed",
        )

    creator = await creator_repo.get_by_id(collab.creator_id)
    if creator:
        await notification_service.create_notification(
            profile_id=creator.profile_id,
            type=NotificationType.COLLABORATION_COMPLETED,
            title="Payment confirmed",
            body="The business confirmed they've paid you and marked this collaboration complete.",
            related_id=collaboration_id,
        )

    await chat_service.post_collaboration_event(
        collaboration_id,
        profile_id,
        "payment_confirmed",
        "Confirmed payment. This collaboration is complete.",
    )

    return _collaboration_to_response(updated)
