"""
Post-collaboration reviews.

Reviews are always anchored to a completed collaboration rather than being
free-floating profile ratings — that's what makes them trustworthy, and it
gives a natural authorization rule: you may review someone precisely when
you finished a piece of work with them.
"""

import logging

from fastapi import HTTPException, status

from app.core.enums import CollaborationStatus
from app.repositories.business_repo import BusinessRepository
from app.repositories.collaboration_repo import CollaborationRepository
from app.repositories.creator_repo import CreatorRepository
from app.repositories.review_repo import ReviewRepository
from app.schemas.review import RatingSummaryResponse, ReviewCreateRequest, ReviewResponse

logger = logging.getLogger(__name__)


def _to_response(row: dict) -> ReviewResponse:
    return ReviewResponse(
        id=row["id"],
        collaboration_id=row["collaboration_id"],
        reviewer_profile_id=row["reviewer_profile_id"],
        reviewee_profile_id=row["reviewee_profile_id"],
        rating=row["rating"],
        comment=row.get("comment"),
        created_at=row["created_at"],
    )


async def _resolve_participants(
    collaboration_id: str,
    profile_id: str,
    *,
    collab_repo: CollaborationRepository,
    creator_repo: CreatorRepository,
    business_repo: BusinessRepository,
) -> str:
    """Authorize the reviewer and return the profile id they're reviewing.

    Both sides of a collaboration are stored as creator_id/business_id, so
    the caller's profile has to be resolved to one of those to work out
    which side they are — and therefore who the counterparty is.
    """
    collab = await collab_repo.get_by_id(collaboration_id)
    if not collab:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collaboration not found")

    # Only completed work is reviewable. Reviewing mid-flight would let a
    # rating be used as leverage during an active negotiation.
    if collab.status != CollaborationStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You can only review a collaboration once it's completed",
        )

    creator = await creator_repo.get_by_id(collab.creator_id)
    business = await business_repo.get_by_id(collab.business_id)
    if not creator or not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collaboration participants not found",
        )

    if creator.profile_id == profile_id:
        return business.profile_id
    if business.profile_id == profile_id:
        return creator.profile_id

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You are not part of this collaboration",
    )


async def submit_review(
    collaboration_id: str,
    profile_id: str,
    data: ReviewCreateRequest,
    *,
    repo: ReviewRepository | None = None,
    collab_repo: CollaborationRepository | None = None,
    creator_repo: CreatorRepository | None = None,
    business_repo: BusinessRepository | None = None,
) -> ReviewResponse:
    """Create or update the caller's review of the other party.

    Idempotent by design: the table has one row per (collaboration,
    reviewer), so submitting again edits the existing review instead of
    failing on the unique constraint or stacking duplicates.
    """
    repo = repo or ReviewRepository()
    collab_repo = collab_repo or CollaborationRepository()
    creator_repo = creator_repo or CreatorRepository()
    business_repo = business_repo or BusinessRepository()

    reviewee_profile_id = await _resolve_participants(
        collaboration_id,
        profile_id,
        collab_repo=collab_repo,
        creator_repo=creator_repo,
        business_repo=business_repo,
    )

    payload = {
        "collaboration_id": collaboration_id,
        "reviewer_profile_id": profile_id,
        "reviewee_profile_id": reviewee_profile_id,
        "rating": data.rating,
        "comment": (data.comment or "").strip() or None,
    }

    existing = await repo.get_by_collaboration_and_reviewer(collaboration_id, profile_id)
    row = (
        await repo.update_review(existing["id"], {
            "rating": payload["rating"],
            "comment": payload["comment"],
        })
        if existing
        else await repo.insert_review(payload)
    )

    if not row:
        logger.error(
            "submit_review: %s returned no row for collaboration_id=%s reviewer_profile_id=%s",
            "update_review" if existing else "insert_review",
            collaboration_id,
            profile_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save the review due to a server error",
        )
    return _to_response(row)


async def get_my_review(
    collaboration_id: str,
    profile_id: str,
    *,
    repo: ReviewRepository | None = None,
) -> ReviewResponse | None:
    """The caller's own review, so the client can show "edit" instead of
    "leave a review" without guessing."""
    repo = repo or ReviewRepository()
    row = await repo.get_by_collaboration_and_reviewer(collaboration_id, profile_id)
    return _to_response(row) if row else None


async def list_reviews_for_profile(
    profile_id: str,
    page: int = 1,
    page_size: int = 20,
    *,
    repo: ReviewRepository | None = None,
) -> dict:
    repo = repo or ReviewRepository()
    rows, total = await repo.list_for_reviewee(profile_id, page=page, page_size=page_size)
    return {
        "items": [_to_response(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_rating_summary(
    profile_id: str,
    *,
    repo: ReviewRepository | None = None,
) -> RatingSummaryResponse:
    repo = repo or ReviewRepository()
    return RatingSummaryResponse(**await repo.rating_summary(profile_id))
