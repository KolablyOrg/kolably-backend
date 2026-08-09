"""
Collaboration routes — managing active collaborations, content submission, completion.
"""

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_current_user, require_role
from app.core.enums import UserRole
from app.schemas.collaboration import CollaborationResponse
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
