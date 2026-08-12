from datetime import UTC, datetime

from fastapi import HTTPException, status

from app.core.enums import CollaborationStatus, NotificationType
from app.models.business import Business
from app.models.campaign import Campaign
from app.models.collaboration import Collaboration
from app.repositories.business_repo import BusinessRepository
from app.repositories.campaign_repo import CampaignRepository
from app.repositories.collaboration_repo import CollaborationRepository
from app.repositories.creator_repo import CreatorRepository
from app.schemas.collaboration import ContentSubmitRequest
from app.services import notification_service


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
) -> str:
    repo = repo or BusinessRepository()
    business_id = await repo.get_id_by_profile_id(profile_id)
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
        business_id = await _get_business_id_for_user(profile_id, repo=business_repo)
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
    *,
    repo: CollaborationRepository | None = None,
    campaign_repo: CampaignRepository | None = None,
    business_repo: BusinessRepository | None = None,
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

    submissions_raw = await repo.list_submissions(collaboration_id)
    submissions = [
        {
            "id": sub["id"],
            "collaboration_id": sub["collaboration_id"],
            "content_url": sub["content_url"],
            "platform": sub["platform"],
            "views": sub.get("views"),
            "likes": sub.get("likes"),
            "comments": sub.get("comments"),
            "synced_at": sub.get("synced_at"),
            "submitted_at": sub["submitted_at"],
        }
        for sub in submissions_raw
    ]

    campaign = await campaign_repo.get_by_id(collab.campaign_id)
    business = await business_repo.get_by_id(collab.business_id)
    resp = _collaboration_to_response(collab, campaign=campaign, business=business)
    resp["content_submissions"] = submissions
    return resp


async def _get_owned_collaboration(
    collaboration_id: str,
    profile_id: str,
    *,
    repo: CollaborationRepository,
    business_repo: BusinessRepository,
) -> Collaboration:
    """Load a collaboration, ensuring the caller is the business side of it —
    only the business marks a collaboration complete or cancelled."""
    collab = await repo.get_by_id(collaboration_id)
    if not collab:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collaboration not found",
        )

    business_id = await _get_business_id_for_user(profile_id, repo=business_repo)
    if collab.business_id != business_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this collaboration",
        )
    return collab


async def complete_collaboration(
    collaboration_id: str,
    profile_id: str,
    *,
    repo: CollaborationRepository | None = None,
    business_repo: BusinessRepository | None = None,
    creator_repo: CreatorRepository | None = None,
) -> dict:
    repo = repo or CollaborationRepository()
    business_repo = business_repo or BusinessRepository()
    creator_repo = creator_repo or CreatorRepository()

    collab = await _get_owned_collaboration(
        collaboration_id, profile_id, repo=repo, business_repo=business_repo
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
) -> dict:
    repo = repo or CollaborationRepository()
    business_repo = business_repo or BusinessRepository()

    collab = await _get_owned_collaboration(
        collaboration_id, profile_id, repo=repo, business_repo=business_repo
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

    Does not attempt to auto-fetch view/like/comment counts from Instagram —
    that would require resolving an arbitrary pasted URL to a media id the
    Graph API recognizes (matching against the creator's own media list,
    handling token expiry, etc.), which is real scope beyond making this
    endpoint exist. views/likes/comments are stored only if the caller
    supplies them; they're null otherwise, same as a fresh, unsynced row.
    """
    repo = repo or CollaborationRepository()
    creator_repo = creator_repo or CreatorRepository()

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

    platform = data.platform.value if hasattr(data.platform, "value") else data.platform
    await repo.insert_submission({
        "collaboration_id": collaboration_id,
        "content_url": data.content_url,
        "platform": platform,
        "views": data.views,
        "likes": data.likes,
        "comments": data.comments,
        "notes": data.notes,
    })

    if collab.status != CollaborationStatus.CONTENT_SUBMITTED:
        updated = await repo.update_status(
            collaboration_id, {"status": CollaborationStatus.CONTENT_SUBMITTED.value}
        )
        if updated:
            collab = updated

    return await get_collaboration(
        collaboration_id, repo=repo, campaign_repo=campaign_repo, business_repo=business_repo
    )
