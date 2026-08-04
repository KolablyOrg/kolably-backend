"""
Business routes — profile, discovery, dashboard.
"""

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_current_user
from app.core.enums import CampaignStatus
from app.schemas.application import ApplicationWithCreator
from app.schemas.business import (
    BusinessResponse,
    BusinessStatsResponse,
    KybStatusResponse,
    KybSubmitRequest,
)
from app.schemas.campaign import CampaignSummary
from app.schemas.common import PaginatedResponse
from app.schemas.user import UserInToken
from app.services import application_service, business_service

router = APIRouter()


@router.get("/", response_model=PaginatedResponse[BusinessResponse])
async def list_businesses(
    search: str | None = Query(None),
    category: str | None = Query(None),
    city: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List and filter businesses."""
    return await business_service.list_businesses(
        search=search,
        category=category,
        city=city,
        page=page,
        page_size=page_size,
    )


@router.get("/me/stats", response_model=BusinessStatsResponse)
async def get_business_stats(
    user: UserInToken = Depends(get_current_user),
):
    """Get stats for the current business."""
    return await business_service.get_business_stats(profile_id=user.id)


@router.get("/me/campaigns", response_model=PaginatedResponse[CampaignSummary])
async def list_my_campaigns(
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: UserInToken = Depends(get_current_user),
):
    """List campaigns for the current business."""
    return await business_service.list_my_campaigns(
        profile_id=user.id,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.get("/me/applications", response_model=PaginatedResponse[ApplicationWithCreator])
async def list_my_applications(
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: UserInToken = Depends(get_current_user),
):
    """List applications for the current business."""
    return await application_service.list_business_applications(
        profile_id=user.id,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.get("/me/verification", response_model=KybStatusResponse)
async def get_verification_status(
    user: UserInToken = Depends(get_current_user),
):
    """Get KYB verification status for the current business."""
    return await business_service.get_kyb_status(profile_id=user.id)


@router.post("/me/verification", response_model=KybStatusResponse)
async def submit_verification(
    data: KybSubmitRequest,
    user: UserInToken = Depends(get_current_user),
):
    """Submit business type, legal entity, PAN/GST, and proof document for KYB verification."""
    return await business_service.submit_kyb_verification(profile_id=user.id, data=data)


@router.get("/{business_id}", response_model=BusinessResponse)
async def get_business(business_id: str) -> BusinessResponse:
    """Get a specific business's public profile."""
    business = await business_service.get_business_by_id(business_id)
    if not business:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")
    return business


@router.get("/{business_id}/campaigns", response_model=PaginatedResponse[CampaignSummary])
async def list_business_campaigns(
    business_id: str,
    status: str | None = Query(CampaignStatus.ACTIVE.value),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List public campaigns for a business (defaults to active only)."""
    return await business_service.list_business_campaigns(
        business_id=business_id,
        status=status,
        page=page,
        page_size=page_size,
    )
