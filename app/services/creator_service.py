from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status

from app.core.crypto import decrypt_token, encrypt_token
from app.core.enums import UserRole
from app.models.campaign import Campaign
from app.models.creator import Creator, PortfolioItem
from app.repositories.campaign_repo import CampaignRepository
from app.repositories.creator_repo import CreatorRepository
from app.schemas.creator import (
    CreatorResponse,
    CreatorStatsResponse,
    CreatorUpdateRequest,
    PortfolioItemCreateRequest,
)
from app.services import instagram_service
from app.services.campaign_service import _campaign_to_response

_TOKEN_REFRESH_THRESHOLD = timedelta(days=10)
_DEFAULT_TOKEN_LIFETIME_SECONDS = 5_184_000  # ~60 days


def _creator_to_response(creator: Creator) -> CreatorResponse:
    """Single source of truth for mapping a Creator model to a CreatorResponse.

    `user_id` is `profile_id` — the FK already IS the profile's id.
    """
    return CreatorResponse(
        id=creator.id,
        user_id=creator.profile_id,
        name=creator.name,
        username=creator.username,
        profile_photo_url=creator.profile_photo_url,
        niche=creator.niche,
        city=creator.city,
        follower_count=creator.follower_count,
        engagement_rate=creator.engagement_rate,
        bio=creator.bio,
        instagram_handle=creator.instagram_handle,
        created_at=creator.created_at,
        tiktok_handle=creator.tiktok_handle,
        instagram_connected=creator.instagram_connected,
        instagram_synced_at=creator.instagram_synced_at,
        website=creator.website,
        following_count=creator.following_count,
    )


async def get_creator_by_id(
    creator_id: str,
    *,
    repo: CreatorRepository | None = None,
) -> CreatorResponse | None:
    repo = repo or CreatorRepository()
    creator = await repo.get_by_id(creator_id)

    if not creator:
        return None

    return _creator_to_response(creator)


async def list_creators(
    search: str | None = None,
    niche: str | None = None,
    city: str | None = None,
    follower_min: int | None = None,
    follower_max: int | None = None,
    page: int = 1,
    page_size: int = 20,
    *,
    repo: CreatorRepository | None = None,
) -> dict:
    repo = repo or CreatorRepository()
    creators, total = await repo.list_filtered(
        search=search,
        niche=niche,
        city=city,
        follower_min=follower_min,
        follower_max=follower_max,
        page=page,
        page_size=page_size,
    )

    return {
        "items": [_creator_to_response(c) for c in creators],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _portfolio_item_to_response(item: PortfolioItem) -> dict:
    return {
        "id": item.id,
        "creator_id": item.creator_id,
        "title": item.title,
        "media_url": item.media_url,
        "post_link": item.post_link,
        "media_type": item.media_type,
        "like_count": item.like_count,
        "comment_count": item.comment_count,
        "created_at": item.created_at,
    }


def _ensure_creator_access(creator: Creator | None, profile_id: str, role: UserRole) -> Creator:
    """Ownership gate for write paths — the service-role client bypasses RLS,
    so this check is the only backstop. 404 if the creator doesn't exist
    (don't leak existence), 403 if it exists but belongs to someone else.
    Superadmins can act on any creator profile.
    """
    if not creator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator not found",
        )
    if role != UserRole.SUPERADMIN and creator.profile_id != profile_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this creator profile",
        )
    return creator


async def update_creator(
    creator_id: str,
    profile_id: str,
    role: UserRole,
    data: CreatorUpdateRequest,
    *,
    repo: CreatorRepository | None = None,
) -> CreatorResponse:
    """Update a creator's profile (owner or superadmin). Only provided
    (non-None) fields are written; Instagram-owned fields (website,
    following_count, engagement stats) are not updatable here — they come
    from connect/sync. `follower_count` is self-reportable UNTIL Instagram
    is connected, after which it's Instagram-verified and this rejects
    attempts to override it — otherwise a connected creator could inflate
    it and nothing would resync it until the next explicit `sync` call."""
    repo = repo or CreatorRepository()
    creator = await repo.get_by_id(creator_id)
    _ensure_creator_access(creator, profile_id, role)

    if data.follower_count is not None and creator.instagram_access_token:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="follower_count is managed by your connected Instagram account — use sync instead",
        )

    update_data = data.model_dump(exclude_none=True)
    if not update_data:
        return _creator_to_response(creator)

    updated = await repo.update_creator(creator_id, update_data)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator not found",
        )
    return _creator_to_response(updated)


async def add_portfolio_item(
    creator_id: str,
    profile_id: str,
    role: UserRole,
    data: PortfolioItemCreateRequest,
    *,
    repo: CreatorRepository | None = None,
) -> dict:
    repo = repo or CreatorRepository()
    creator = await repo.get_by_id(creator_id)
    _ensure_creator_access(creator, profile_id, role)

    item = await repo.insert_portfolio_item({
        "creator_id": creator_id,
        **data.model_dump(),
    })
    if not item:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add portfolio item",
        )
    return _portfolio_item_to_response(item)


async def delete_portfolio_item(
    creator_id: str,
    item_id: str,
    profile_id: str,
    role: UserRole,
    *,
    repo: CreatorRepository | None = None,
) -> None:
    repo = repo or CreatorRepository()
    creator = await repo.get_by_id(creator_id)
    _ensure_creator_access(creator, profile_id, role)

    item = await repo.get_portfolio_item(item_id)
    if not item or item.creator_id != creator_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio item not found",
        )
    await repo.delete_portfolio_item(item_id, creator_id)


async def save_campaign(
    profile_id: str,
    campaign_id: str,
    *,
    repo: CreatorRepository | None = None,
    campaign_repo: CampaignRepository | None = None,
) -> None:
    """Bookmark a campaign for the current creator. Idempotent — saving an
    already-saved campaign is a no-op (the PK is (creator_id, campaign_id))."""
    repo = repo or CreatorRepository()
    creator_id = await repo.get_id_by_profile_id(profile_id)
    if not creator_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator profile not found",
        )

    campaign_repo = campaign_repo or CampaignRepository()
    if not await campaign_repo.get_by_id(campaign_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    await repo.save_campaign(creator_id, campaign_id)


async def unsave_campaign(
    profile_id: str,
    campaign_id: str,
    *,
    repo: CreatorRepository | None = None,
) -> None:
    """Remove a bookmark. Idempotent — unsaving something not saved is a no-op."""
    repo = repo or CreatorRepository()
    creator_id = await repo.get_id_by_profile_id(profile_id)
    if not creator_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator profile not found",
        )
    await repo.unsave_campaign(creator_id, campaign_id)


async def get_creator_portfolio(
    creator_id: str,
    media_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
    *,
    repo: CreatorRepository | None = None,
) -> dict:
    repo = repo or CreatorRepository()
    items, total = await repo.list_portfolio(
        creator_id=creator_id,
        media_type=media_type,
        page=page,
        page_size=page_size,
    )

    return {
        "items": [_portfolio_item_to_response(item) for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_creator_stats(
    profile_id: str,
    *,
    repo: CreatorRepository | None = None,
) -> CreatorStatsResponse:
    repo = repo or CreatorRepository()
    creator_id = await repo.get_id_by_profile_id(profile_id)

    if not creator_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator profile not found",
        )

    active_count = await repo.count_active_collaborations(creator_id)

    return CreatorStatsResponse(
        active_collaborations_count=active_count,
        engagement_growth_pct=None,
    )


async def list_saved_campaigns(
    profile_id: str,
    page: int = 1,
    page_size: int = 20,
    *,
    repo: CreatorRepository | None = None,
) -> dict:
    repo = repo or CreatorRepository()
    creator_id = await repo.get_id_by_profile_id(profile_id)

    if not creator_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator profile not found",
        )

    rows, total = await repo.list_saved_campaigns(
        creator_id=creator_id,
        page=page,
        page_size=page_size,
    )

    items = []
    for row in rows:
        campaign_row = row.get("campaigns")
        if campaign_row:
            campaign = Campaign.from_row(campaign_row)
            items.append(_campaign_to_response(campaign))

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ── Instagram connection (Google/email signups connecting during onboarding) ──


def _no_creator_profile() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator profile not found")


def _not_connected() -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Instagram not connected")


async def get_instagram_auth_url(redirect_uri: str) -> dict:
    return {"url": instagram_service.build_authorize_url(redirect_uri)}


async def connect_instagram(
    profile_id: str,
    code: str,
    redirect_uri: str,
    *,
    repo: CreatorRepository | None = None,
) -> CreatorResponse:
    """Exchange the OAuth `code`, pre-fill the profile from Instagram, and store
    the token. One-time full pre-fill — same fields `/auth/instagram` signup
    populates for a brand-new creator (see `instagram_service.build_profile_prefill`).
    """
    repo = repo or CreatorRepository()
    creator = await repo.get_by_profile_id(profile_id)
    if not creator:
        raise _no_creator_profile()

    short_lived = await instagram_service.exchange_code_for_token(code, redirect_uri)
    long_lived = await instagram_service.exchange_for_long_lived_token(short_lived["access_token"])
    access_token = long_lived["access_token"]

    ig_profile = await instagram_service.fetch_profile(access_token)

    if ig_profile.get("account_type") == "PERSONAL":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Convert your Instagram account to a Business or Creator account first",
        )

    instagram_user_id = str(ig_profile["user_id"])
    other = await repo.get_by_instagram_user_id(instagram_user_id)
    if other and other.profile_id != profile_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This Instagram account is already connected to a different Kolably account",
        )

    media = await instagram_service.fetch_media(access_token)
    engagement_rate = await instagram_service.calculate_engagement_rate(access_token, media)
    expires_at = datetime.now(UTC) + timedelta(seconds=long_lived.get("expires_in", _DEFAULT_TOKEN_LIFETIME_SECONDS))
    now = datetime.now(UTC).isoformat()

    updated = await repo.update_by_profile_id(profile_id, {
        "instagram_handle": ig_profile["username"],
        "instagram_user_id": instagram_user_id,
        "instagram_access_token": encrypt_token(access_token),
        "instagram_token_expires_at": expires_at.isoformat(),
        "instagram_synced_at": now,
        **instagram_service.build_profile_prefill(ig_profile, engagement_rate),
    })

    return _creator_to_response(updated)


async def sync_instagram(
    profile_id: str,
    *,
    repo: CreatorRepository | None = None,
) -> CreatorResponse:
    """Re-fetch the stats subset only (follower/following count, photo,
    engagement rate) — name/bio/website stay as connect-time pre-filled them,
    matching the connect-once/sync-stats-only split in API_REQUIREMENTS.md §2.

    Also proactively refreshes the long-lived token if it's close to
    expiring (<10 days left), so a creator who never revisits doesn't
    silently lose their connection at the 60-day mark.
    """
    repo = repo or CreatorRepository()
    creator = await repo.get_by_profile_id(profile_id)
    if not creator or not creator.instagram_access_token:
        raise _not_connected()

    access_token = decrypt_token(creator.instagram_access_token)
    expires_at = _parse_expiry(creator.instagram_token_expires_at)

    if expires_at is None or expires_at - datetime.now(UTC) < _TOKEN_REFRESH_THRESHOLD:
        refreshed = await instagram_service.refresh_long_lived_token(access_token)
        access_token = refreshed["access_token"]
        expires_at = datetime.now(UTC) + timedelta(
            seconds=refreshed.get("expires_in", _DEFAULT_TOKEN_LIFETIME_SECONDS)
        )

    ig_profile = await instagram_service.fetch_profile(access_token)
    media = await instagram_service.fetch_media(access_token)
    engagement_rate = await instagram_service.calculate_engagement_rate(access_token, media)

    updated = await repo.update_by_profile_id(profile_id, {
        "follower_count": ig_profile.get("followers_count"),
        "following_count": ig_profile.get("follows_count"),
        "profile_photo_url": ig_profile.get("profile_picture_url"),
        "engagement_rate": engagement_rate,
        "instagram_access_token": encrypt_token(access_token),
        "instagram_token_expires_at": expires_at.isoformat(),
        "instagram_synced_at": datetime.now(UTC).isoformat(),
    })

    return _creator_to_response(updated)


async def disconnect_instagram(
    profile_id: str,
    *,
    repo: CreatorRepository | None = None,
) -> None:
    """Clear the stored connection. Local-only — Instagram Login has no public
    token-revocation endpoint; the creator can revoke app access themselves
    from their Instagram/Facebook account settings if they want to fully
    de-authorize Kolably.
    """
    repo = repo or CreatorRepository()
    creator = await repo.get_by_profile_id(profile_id)
    if not creator:
        raise _no_creator_profile()

    await repo.update_by_profile_id(profile_id, {
        "instagram_user_id": None,
        "instagram_access_token": None,
        "instagram_token_expires_at": None,
        "instagram_synced_at": None,
    })


async def import_instagram_portfolio(
    profile_id: str,
    *,
    repo: CreatorRepository | None = None,
) -> list[dict]:
    repo = repo or CreatorRepository()
    creator = await repo.get_by_profile_id(profile_id)
    if not creator or not creator.instagram_access_token:
        raise _not_connected()

    access_token = decrypt_token(creator.instagram_access_token)
    media = await instagram_service.fetch_media(access_token)

    if not media:
        return []

    items = instagram_service.build_portfolio_items(creator.id, media)
    inserted = await repo.insert_portfolio_items(items)
    return [_portfolio_item_to_response(item) for item in inserted]


def _parse_expiry(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)
