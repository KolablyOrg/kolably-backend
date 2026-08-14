"""
Collaboration routes — managing active collaborations, content submission, completion.
"""

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_current_user, require_role
from app.core.enums import UserRole
from app.schemas.collaboration import (
    CollaborationResponse,
    ContentSubmitRequest,
    RequestRevisionRequest,
)
from app.schemas.common import PaginatedResponse
from app.schemas.user import UserInToken
from app.services import collaboration_service

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
    collaboration_id: str,
    user: UserInToken = Depends(get_current_user),
):
    """Get collaboration details."""
    return await collaboration_service.get_collaboration(collaboration_id)


@router.patch(
    "/{collaboration_id}/complete",
    response_model=CollaborationResponse,
    dependencies=[Depends(require_role(UserRole.BUSINESS, UserRole.SUPERADMIN))],
)
async def complete_collaboration(
    collaboration_id: str,
    user: UserInToken = Depends(get_current_user),
):
    """Mark a collaboration as completed (business owner only)."""
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
    user: UserInToken = Depends(get_current_user),
):
    """Business approves a submitted draft — creator can now post it live
    (business owner only)."""
    return await collaboration_service.approve_draft(
        collaboration_id=collaboration_id,
        profile_id=user.id,
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
    """Business confirms they paid the creator directly, completing the
    collaboration (business owner only)."""
    return await collaboration_service.confirm_payment(
        collaboration_id=collaboration_id,
        profile_id=user.id,
    )
