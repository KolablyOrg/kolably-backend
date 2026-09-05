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
    BulkDeletePortfolioRequest,
    CreatorPublicResponse,
    CreatorResponse,
    CreatorStatsResponse,
    CreatorUpdateRequest,
    IdentityStatusResponse,
    IdentitySubmitRequest,
    InstagramAuthUrlResponse,
    InstagramConnectRequest,
    InstagramImportRequest,
    InstagramMediaPreviewItem,
    PayoutResponse,
    PayoutSetupRequest,
    PortfolioItemCreateRequest,
    PortfolioItemResponse,
)
from app.schemas.review import RatingSummaryResponse
from app.schemas.user import UserInToken
from app.services import creator_service, review_service

router = APIRouter()


@router.get(
    "/me/stats",
    response_model=CreatorStatsResponse,
    dependencies=[Depends(require_role(UserRole.CREATOR))],
)
async def get_creator_stats(
    days: int = Query(7, ge=1),
    user: UserInToken = Depends(get_current_user),
):
    """Get stats for the current creator."""
    return await creator_service.get_creator_stats(profile_id=user.id, days=days)


@router.get(
    "/me/saved-campaigns",
    response_model=PaginatedResponse[CampaignResponse],
    dependencies=[Depends(require_role(UserRole.CREATOR))],
)
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


@router.get(
    "/me/instagram/auth-url",
    response_model=InstagramAuthUrlResponse,
    dependencies=[Depends(require_role(UserRole.CREATOR))],
)
async def get_instagram_auth_url(
    redirect_uri: str = Query(..., description="Where Instagram should redirect back to after consent"),
    user: UserInToken = Depends(get_current_user),
):
    """Get the Instagram OAuth authorization URL to redirect the client to."""
    return await creator_service.get_instagram_auth_url(redirect_uri)


@router.post(
    "/me/instagram/connect",
    response_model=CreatorResponse,
    dependencies=[Depends(require_role(UserRole.CREATOR))],
)
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


@router.post(
    "/me/instagram/sync",
    response_model=CreatorResponse,
    dependencies=[Depends(require_role(UserRole.CREATOR))],
)
async def sync_instagram(
    user: UserInToken = Depends(get_current_user),
):
    """Re-fetch follower/following count, photo, and engagement rate from Instagram."""
    return await creator_service.sync_instagram(profile_id=user.id)


@router.delete(
    "/me/instagram/disconnect",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.CREATOR))],
)
async def disconnect_instagram(
    user: UserInToken = Depends(get_current_user),
):
    """Disconnect Instagram — clears the stored token locally."""
    await creator_service.disconnect_instagram(profile_id=user.id)


@router.get(
    "/me/instagram/media-preview",
    response_model=list[InstagramMediaPreviewItem],
    dependencies=[Depends(require_role(UserRole.CREATOR))],
)
async def preview_instagram_media(
    user: UserInToken = Depends(get_current_user),
):
    """Preview recent Instagram media without importing it, so the creator
    can choose which posts/reels to add to their portfolio."""
    return await creator_service.preview_instagram_media(profile_id=user.id)


@router.post(
    "/me/instagram/import-portfolio",
    response_model=list[PortfolioItemResponse],
    dependencies=[Depends(require_role(UserRole.CREATOR))],
)
async def import_instagram_portfolio(
    data: InstagramImportRequest = InstagramImportRequest(),
    user: UserInToken = Depends(get_current_user),
):
    """Import Instagram media into the creator's portfolio — specific items
    if `media_ids` is given, otherwise everything."""
    return await creator_service.import_instagram_portfolio(profile_id=user.id, media_ids=data.media_ids)


# ── Payout & Tax Setup ──────────────────────────────────
@router.get(
    "/me/payout",
    response_model=PayoutResponse,
    dependencies=[Depends(require_role(UserRole.CREATOR))],
)
async def get_payout_details(
    user: UserInToken = Depends(get_current_user),
):
    """Get payout & tax details for current creator."""
    return await creator_service.get_payout_details(profile_id=user.id)


@router.post(
    "/me/payout",
    response_model=PayoutResponse,
    dependencies=[Depends(require_role(UserRole.CREATOR))],
)
async def save_payout_details(
    data: PayoutSetupRequest,
    user: UserInToken = Depends(get_current_user),
):
    """Save & verify payout method (Bank or UPI) + PAN/GST details."""
    return await creator_service.save_payout_details(profile_id=user.id, data=data)


# ── Identity Verification ──────────────────────────────
@router.get(
    "/me/identity",
    response_model=IdentityStatusResponse,
    dependencies=[Depends(require_role(UserRole.CREATOR))],
)
async def get_identity_status(
    user: UserInToken = Depends(get_current_user),
):
    """Get identity verification status for current creator."""
    return await creator_service.get_identity_status(profile_id=user.id)


@router.post(
    "/me/identity",
    response_model=IdentityStatusResponse,
    dependencies=[Depends(require_role(UserRole.CREATOR))],
)
async def submit_identity_verification(
    data: IdentitySubmitRequest,
    user: UserInToken = Depends(get_current_user),
):
    """Submit PAN and document for identity verification."""
    return await creator_service.submit_identity_verification(profile_id=user.id, data=data)


@router.get("/", response_model=PaginatedResponse[CreatorPublicResponse])
async def list_creators(
    search: str | None = Query(None),
    niche: str | None = Query(None),
    city: list[str] | None = Query(None),
    follower_min: int | None = Query(None),
    follower_max: int | None = Query(None),
    engagement_min: float | None = Query(None, ge=0),
    verified_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List and filter discoverable creators for brand search."""
    return await creator_service.list_creators(
        search=search,
        niche=niche,
        city=city,
        follower_min=follower_min,
        follower_max=follower_max,
        engagement_min=engagement_min,
        verified_only=verified_only,
        page=page,
        page_size=page_size,
    )


@router.get("/locations", response_model=PaginatedResponse[str])
async def get_creator_locations():
    """Distinct cities from discoverable creators (for brand Discover filter pills)."""
    return await creator_service.get_locations()


@router.get("/niches", response_model=PaginatedResponse[str])
async def get_creator_niches():
    """Distinct niches from discoverable creators (for brand Discover filter pills)."""
    return await creator_service.get_niches()


@router.get("/{creator_id}", response_model=CreatorPublicResponse)
async def get_creator(creator_id: str):
    """Get a specific creator's public profile."""
    creator = await creator_service.get_creator_by_id(creator_id)
    if not creator:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator not found")
    return creator


@router.get("/{creator_id}/rating", response_model=RatingSummaryResponse)
async def get_creator_rating(creator_id: str) -> RatingSummaryResponse:
    """Aggregate rating left by businesses after completed collaborations —
    `average_rating` is null (not 0) when nobody has reviewed yet."""
    creator = await creator_service.get_creator_by_id(creator_id)
    if not creator:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator not found")
    return await review_service.get_rating_summary(creator.user_id)


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
    """Add a portfolio item (owner or superadmin only).

    `media_url` may be a public storage URL for a locally uploaded asset or
    an external Instagram/source URL for imported content.
    """
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


@router.delete(
    "/{creator_id}/portfolio",
    dependencies=[Depends(require_role(UserRole.CREATOR, UserRole.SUPERADMIN))],
)
async def bulk_delete_portfolio_items(
    creator_id: str,
    request: BulkDeletePortfolioRequest,
    user: UserInToken = Depends(get_current_user),
):
    """Bulk delete portfolio items (owner or superadmin only)."""
    await creator_service.bulk_delete_portfolio_items(
        creator_id=creator_id,
        item_ids=request.item_ids,
        profile_id=user.id,
        role=user.role,
    )
    return {"status": "success", "deleted": len(request.item_ids)}
