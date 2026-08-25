"""
Collaboration routes — managing active collaborations, content submission, completion.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_current_user, require_role
from app.core.enums import UserRole
from app.schemas.collaboration import (
    ApproveSubmissionRequest,
    CollaborationResponse,
    ContentSubmitRequest,
    RequestRevisionRequest,
)
from app.schemas.common import PaginatedResponse
from app.schemas.review import ReviewCreateRequest, ReviewResponse
from app.schemas.user import UserInToken
from app.services import collaboration_service, review_service

router = APIRouter()


@router.get("/", response_model=PaginatedResponse[CollaborationResponse])
async def list_collaborations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    campaign_id: str | None = Query(None),
    user: UserInToken = Depends(get_current_user),
):
    """List collaborations for the current user (filtered by role)."""
    return await collaboration_service.list_collaborations(
        profile_id=user.id,
        role=user.role.value,
        page=page,
        page_size=page_size,
        campaign_id=campaign_id,
    )


@router.get("/{collaboration_id}", response_model=CollaborationResponse)
async def get_collaboration(
    # UUID (not str): FastAPI validates the path segment itself and returns
    # a clean 422 for a malformed id, instead of a non-UUID string reaching
    # the DB layer and coming back as an unhandled 500.
    collaboration_id: UUID,
    user: UserInToken = Depends(get_current_user),
):
    """Get collaboration details."""
    return await collaboration_service.get_collaboration(
        str(collaboration_id), profile_id=user.id, role=user.role.value
    )


@router.patch(
    "/{collaboration_id}/complete",
    response_model=CollaborationResponse,
    dependencies=[Depends(require_role(UserRole.SUPERADMIN))],
)
async def complete_collaboration(
    collaboration_id: str,
    user: UserInToken = Depends(get_current_user),
):
    """Force-close a collaboration — superadmin support override only.

    BUSINESS was deliberately removed from this guard on 2026-08-25. A
    business closing a collaboration on its own say-so is exactly the bug
    this endpoint used to enable: the creator had no way to dispute it and
    nothing in the system evidenced that payment actually happened. The
    supported path is POST /confirm-payment (business) followed by
    POST /confirm-completion (creator).
    """
    return await collaboration_service.complete_collaboration(
        collaboration_id=collaboration_id,
        profile_id=user.id,
    )


@router.patch(
    "/{collaboration_id}/cancel",
    response_model=CollaborationResponse,
    dependencies=[Depends(require_role(UserRole.BUSINESS, UserRole.SUPERADMIN))],
)
async def cancel_collaboration(
    collaboration_id: str,
    user: UserInToken = Depends(get_current_user),
):
    """Cancel a collaboration (business owner only)."""
    return await collaboration_service.cancel_collaboration(
        collaboration_id=collaboration_id,
        profile_id=user.id,
    )


@router.post(
    "/{collaboration_id}/submit",
    response_model=CollaborationResponse,
    dependencies=[Depends(require_role(UserRole.CREATOR))],
)
async def submit_content(
    collaboration_id: str,
    data: ContentSubmitRequest,
    user: UserInToken = Depends(get_current_user),
):
    """Creator submits a post/reel link for brand review — a draft cut
    pre-approval, or (once approved) the live published post."""
    return await collaboration_service.submit_content(
        collaboration_id=collaboration_id,
        profile_id=user.id,
        data=data,
    )


@router.post(
    "/{collaboration_id}/request-revision",
    response_model=CollaborationResponse,
    dependencies=[Depends(require_role(UserRole.BUSINESS, UserRole.SUPERADMIN))],
)
async def request_revision(
    collaboration_id: str,
    data: RequestRevisionRequest,
    user: UserInToken = Depends(get_current_user),
):
    """Business asks for changes on a submitted draft (business owner only)."""
    return await collaboration_service.request_revision(
        collaboration_id=collaboration_id,
        profile_id=user.id,
        data=data,
    )


@router.post(
    "/{collaboration_id}/approve",
    response_model=CollaborationResponse,
    dependencies=[Depends(require_role(UserRole.BUSINESS, UserRole.SUPERADMIN))],
)
async def approve_draft(
    collaboration_id: str,
    data: ApproveSubmissionRequest,
    user: UserInToken = Depends(get_current_user),
):
    """Business approves one submitted draft deliverable (business owner only)."""
    return await collaboration_service.approve_draft(
        collaboration_id=collaboration_id,
        profile_id=user.id,
        data=data,
    )


@router.post(
    "/{collaboration_id}/verify-live",
    response_model=CollaborationResponse,
    dependencies=[Depends(require_role(UserRole.BUSINESS, UserRole.SUPERADMIN))],
)
async def verify_live_post(
    collaboration_id: str,
    user: UserInToken = Depends(get_current_user),
):
    """Best-effort automated check of the creator's live post (business owner only)."""
    return await collaboration_service.verify_live_post(
        collaboration_id=collaboration_id,
        profile_id=user.id,
    )


@router.post(
    "/{collaboration_id}/confirm-payment",
    response_model=CollaborationResponse,
    dependencies=[Depends(require_role(UserRole.BUSINESS, UserRole.SUPERADMIN))],
)
async def confirm_payment(
    collaboration_id: str,
    user: UserInToken = Depends(get_current_user),
):
    """Business confirms they paid the creator directly (business owner only).

    Moves the collaboration to `payment_confirmed` — it does NOT complete
    it. The creator closes it by confirming receipt via
    POST /{id}/confirm-completion, or the daily sweep closes it after 7 days
    of no response.
    """
    return await collaboration_service.confirm_payment(
        collaboration_id=collaboration_id,
        profile_id=user.id,
    )


@router.post(
    "/{collaboration_id}/confirm-completion",
    response_model=CollaborationResponse,
    dependencies=[Depends(require_role(UserRole.CREATOR))],
)
async def confirm_completion(
    collaboration_id: str,
    user: UserInToken = Depends(get_current_user),
):
    """Creator confirms they received payment, completing the collaboration.

    Creator-only by design — the party owed the money is the one who
    confirms it arrived. Requires the collaboration to be in
    `payment_confirmed`.
    """
    return await collaboration_service.confirm_completion(
        collaboration_id=collaboration_id,
        profile_id=user.id,
    )


# ── Reviews ───────────────────────────────────────────

@router.post("/{collaboration_id}/review", response_model=ReviewResponse)
async def submit_review(
    collaboration_id: str,
    data: ReviewCreateRequest,
    user: UserInToken = Depends(get_current_user),
):
    """Rate the other party after a completed collaboration.

    Works in both directions — who is being reviewed is derived from which
    side of the collaboration the caller is on, never from the request body.
    Submitting again edits the existing review rather than adding a second.
    """
    return await review_service.submit_review(
        collaboration_id=collaboration_id,
        profile_id=user.id,
        data=data,
    )


@router.get("/{collaboration_id}/review", response_model=ReviewResponse | None)
async def get_my_review(
    collaboration_id: str,
    user: UserInToken = Depends(get_current_user),
):
    """The caller's own review for this collaboration, or null — lets the
    client show "edit your review" instead of offering a duplicate."""
    return await review_service.get_my_review(
        collaboration_id=collaboration_id,
        profile_id=user.id,
    )
