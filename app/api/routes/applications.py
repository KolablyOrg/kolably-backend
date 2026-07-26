"""
Application routes — creators apply to campaigns, businesses accept/reject.
"""

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_current_user, require_role
from app.core.enums import UserRole
from app.schemas.application import ApplicationResponse, ApplicationWithCampaign
from app.schemas.common import PaginatedResponse
from app.schemas.user import UserInToken
from app.services import application_service

router = APIRouter()


@router.get(
    "/me/sent",
    response_model=PaginatedResponse[ApplicationWithCampaign],
    dependencies=[Depends(require_role(UserRole.CREATOR))],
)
async def list_my_applications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: UserInToken = Depends(get_current_user),
):
    """List all applications sent by the current creator."""
    return await application_service.list_my_applications(
        profile_id=user.id,
        page=page,
        page_size=page_size,
    )


@router.get("/{application_id}", response_model=ApplicationResponse)
async def get_application(
    application_id: str,
    user: UserInToken = Depends(get_current_user),
):
    """Get application details."""
    return await application_service.get_application(application_id)
