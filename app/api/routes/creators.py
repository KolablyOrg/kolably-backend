"""
Creator routes — profile, discovery, Instagram integration, dashboard.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.dependencies import (
    get_current_user,
    require_instagram_connected,
    require_role,
)
from app.core.enums import UserRole
from app.schemas.campaign import CampaignResponse
from app.schemas.common import PaginatedResponse
from app.schemas.creator import (
    CreatorResponse,
    CreatorStatsResponse,
    CreatorUpdateRequest,
    InstagramAuthUrlResponse,
    InstagramConnectRequest,
    PortfolioItemCreateRequest,
    PortfolioItemResponse,
)
from app.schemas.user import UserInToken
from app.services import creator_service

router = APIRouter()


@router.get("/me/stats", response_model=CreatorStatsResponse)
async def get_creator_stats(
    user: UserInToken = Depends(get_current_user),
):
    """Get stats for the current creator."""
    return await creator_service.get_creator_stats(profile_id=user.id)


@router.get("/me/saved-campaigns", response_model=PaginatedResponse[CampaignResponse])
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


@router.post(
    "/me/saved-campaigns/{campaign_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(require_role(UserRole.CREATOR)),
        Depends(require_instagram_connected),
    ],
)
async def save_campaign(
    campaign_id: str,
    user: UserInToken = Depends(get_current_user),
):
    """Save (bookmark) a campaign for the current creator. Idempotent."""
    await creator_service.save_campaign(profile_id=user.id, campaign_id=campaign_id)


@router.delete(
    "/me/saved-campaigns/{campaign_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.CREATOR))],
)
async def unsave_campaign(
    campaign_id: str,
    user: UserInToken = Depends(get_current_user),
):
    """Remove a saved campaign for the current creator. Idempotent."""
    await creator_service.unsave_campaign(profile_id=user.id, campaign_id=campaign_id)


@router.get("/me/instagram/auth-url", response_model=InstagramAuthUrlResponse)
async def get_instagram_auth_url(
    redirect_uri: str = Query(..., description="Where Instagram should redirect back to after consent"),
    user: UserInToken = Depends(get_current_user),
):
    """Get the Instagram OAuth authorization URL to redirect the client to."""
    return await creator_service.get_instagram_auth_url(redirect_uri)


@router.post("/me/instagram/connect", response_model=CreatorResponse)
async def connect_instagram(
    data: InstagramConnectRequest,
    user: UserInToken = Depends(get_current_user),
):
    """Connect Instagram to the current (already signed-up) creator account.

    One-time full profile pre-fill from Instagram — for creators who signed
    up via Google/email and are completing the mandatory onboarding step
    (see `require_instagram_connected` in app/core/dependencies.py).
    """
    return await creator_service.connect_instagram(
        profile_id=user.id,
        code=data.code,
        redirect_uri=data.redirect_uri,
    )


@router.post("/me/instagram/sync", response_model=CreatorResponse)
async def sync_instagram(
    user: UserInToken = Depends(get_current_user),
):
    """Re-fetch follower/following count, photo, and engagement rate from Instagram."""
    return await creator_service.sync_instagram(profile_id=user.id)


@router.delete("/me/instagram/disconnect", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_instagram(
    user: UserInToken = Depends(get_current_user),
):
    """Disconnect Instagram — clears the stored token locally."""
    await creator_service.disconnect_instagram(profile_id=user.id)


@router.post("/me/instagram/import-portfolio", response_model=list[PortfolioItemResponse])
async def import_instagram_portfolio(
    user: UserInToken = Depends(get_current_user),
):
    """Import recent Instagram media into the creator's portfolio."""
    return await creator_service.import_instagram_portfolio(profile_id=user.id)


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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator not found")
    return creator


@router.patch(
    "/{creator_id}",
    response_model=CreatorResponse,
    dependencies=[Depends(require_role(UserRole.CREATOR, UserRole.SUPERADMIN))],
)
async def update_creator(
    creator_id: str,
    data: CreatorUpdateRequest,
    user: UserInToken = Depends(get_current_user),
):
    """Update a creator's profile (owner or superadmin only)."""
    return await creator_service.update_creator(
        creator_id=creator_id,
        profile_id=user.id,
        role=user.role,
        data=data,
    )


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


@router.post(
    "/{creator_id}/portfolio",
    response_model=PortfolioItemResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.CREATOR, UserRole.SUPERADMIN))],
)
async def add_portfolio_item(
    creator_id: str,
    data: PortfolioItemCreateRequest,
    user: UserInToken = Depends(get_current_user),
):
    """Add a portfolio item (owner or superadmin only). `media_url` is the
    Supabase Storage URL the client uploaded to directly."""
    return await creator_service.add_portfolio_item(
        creator_id=creator_id,
        profile_id=user.id,
        role=user.role,
        data=data,
    )


@router.delete(
    "/{creator_id}/portfolio/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.CREATOR, UserRole.SUPERADMIN))],
)
async def delete_portfolio_item(
    creator_id: str,
    item_id: str,
    user: UserInToken = Depends(get_current_user),
):
    """Delete a portfolio item (owner or superadmin only)."""
    await creator_service.delete_portfolio_item(
        creator_id=creator_id,
        item_id=item_id,
        profile_id=user.id,
        role=user.role,
    )
