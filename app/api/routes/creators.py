"""
Creator routes — profile, discovery, Instagram integration, dashboard.
"""

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_current_user
from app.schemas.common import PaginatedResponse
from app.schemas.creator import CreatorResponse, CreatorStatsResponse, PortfolioItemResponse
from app.schemas.user import UserInToken
from app.services import creator_service

router = APIRouter()


@router.get("/me/stats", response_model=CreatorStatsResponse)
async def get_creator_stats(
    user: UserInToken = Depends(get_current_user),
):
    """Get stats for the current creator."""
    return await creator_service.get_creator_stats(profile_id=user.id)


@router.get("/me/saved-campaigns", response_model=PaginatedResponse)
async def list_saved_campaigns(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: UserInToken = Depends(get_current_user),
):
    """List saved campaigns for the current creator."""
    return await creator_service.list_saved_campaigns(
        profile_id=user.id,
        page=page,
        page_size=page_size,
    )


@router.get("/", response_model=PaginatedResponse[CreatorResponse])
async def list_creators(
    search: str | None = Query(None),
    niche: str | None = Query(None),
    city: str | None = Query(None),
    follower_min: int | None = Query(None),
    follower_max: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List and filter creators."""
    return await creator_service.list_creators(
        search=search,
        niche=niche,
        city=city,
        follower_min=follower_min,
        follower_max=follower_max,
        page=page,
        page_size=page_size,
    )


@router.get("/{creator_id}", response_model=CreatorResponse)
async def get_creator(creator_id: str):
    """Get a specific creator's public profile."""
    creator = await creator_service.get_creator_by_id(creator_id)
    if not creator:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator not found")
    return creator


@router.get("/{creator_id}/portfolio", response_model=PaginatedResponse[PortfolioItemResponse])
async def get_creator_portfolio(
    creator_id: str,
    media_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Get portfolio items for a creator."""
    return await creator_service.get_creator_portfolio(
        creator_id=creator_id,
        media_type=media_type,
        page=page,
        page_size=page_size,
    )
