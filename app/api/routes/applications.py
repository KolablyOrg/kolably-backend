"""
Application routes — creators apply to campaigns, businesses accept/reject.
"""

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_current_user, require_instagram_connected, require_role
from app.core.enums import UserRole
from app.schemas.application import ApplicationCreateRequest, ApplicationResponse, ApplicationWithCampaign
from app.schemas.common import MessageResponse, PaginatedResponse
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


@router.post(
    "/",
    response_model=ApplicationResponse,
    dependencies=[Depends(require_role(UserRole.CREATOR)), Depends(require_instagram_connected)],
)
async def apply_to_campaign(
    data: ApplicationCreateRequest,
    user: UserInToken = Depends(get_current_user),
):
    """Apply to a campaign as a creator."""
    return await application_service.apply_to_campaign(profile_id=user.id, data=data)


@router.delete(
    "/{application_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_role(UserRole.CREATOR))],
)
async def withdraw_application(
    application_id: str,
    user: UserInToken = Depends(get_current_user),
):
    """Withdraw a pending application the creator sent."""
    return await application_service.withdraw_application(
        application_id=application_id,
        profile_id=user.id,
    )


@router.patch("/{application_id}/accept", response_model=ApplicationResponse)
async def accept_application(
    application_id: str,
    user: UserInToken = Depends(get_current_user),
):
    """Accept an application — the business decides on creator-initiated
    applications, the creator decides on business-sent invites. Creates the
    resulting Collaboration."""
    return await application_service.accept_application(
        application_id=application_id,
        profile_id=user.id,
        role=user.role.value,
    )


@router.patch("/{application_id}/reject", response_model=ApplicationResponse)
async def reject_application(
    application_id: str,
    user: UserInToken = Depends(get_current_user),
):
    """Reject an application/invite — same direction-based authorization as accept."""
    return await application_service.reject_application(
        application_id=application_id,
        profile_id=user.id,
        role=user.role.value,
    )


@router.get("/{application_id}", response_model=ApplicationResponse)
async def get_application(
    application_id: str,
    user: UserInToken = Depends(get_current_user),
):
    """Get application details."""
    return await application_service.get_application(application_id)
