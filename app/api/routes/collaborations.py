"""
Collaboration routes — managing active collaborations, content submission, completion.
"""

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_current_user
from app.schemas.collaboration import CollaborationResponse
from app.schemas.common import PaginatedResponse
from app.schemas.user import UserInToken
from app.services import collaboration_service

router = APIRouter()


@router.get("/", response_model=PaginatedResponse[CollaborationResponse])
async def list_collaborations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: UserInToken = Depends(get_current_user),
):
    """List collaborations for the current user (filtered by role)."""
    return await collaboration_service.list_collaborations(
        profile_id=user.id,
        role=user.role.value,
        page=page,
        page_size=page_size,
    )


@router.get("/{collaboration_id}", response_model=CollaborationResponse)
async def get_collaboration(
    collaboration_id: str,
    user: UserInToken = Depends(get_current_user),
):
    """Get collaboration details."""
    return await collaboration_service.get_collaboration(collaboration_id)
