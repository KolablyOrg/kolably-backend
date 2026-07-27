from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status

from app.core.crypto import decrypt_token, encrypt_token
from app.repositories.creator_repo import CreatorRepository
from app.schemas.creator import CreatorResponse
from app.services import instagram_service

_TOKEN_REFRESH_THRESHOLD = timedelta(days=10)
_DEFAULT_TOKEN_LIFETIME_SECONDS = 5_184_000  # ~60 days


def _row_to_creator_response(row: dict) -> CreatorResponse:
    """Single source of truth for mapping a `creators` row to a CreatorResponse.

    `user_id` is `profile_id` — the FK already IS the profile's id.
    """
    return CreatorResponse(
        id=row["id"],
        user_id=row["profile_id"],
        name=row["name"],
        username=row.get("username"),
        profile_photo_url=row.get("profile_photo_url"),
        niche=row.get("niche"),
        city=row.get("city"),
        follower_count=row.get("follower_count"),
        engagement_rate=row.get("engagement_rate"),
        bio=row.get("bio"),
        created_at=row["created_at"],
        tiktok_handle=row.get("tiktok_handle"),
        instagram_connected=bool(row.get("instagram_user_id") and row.get("instagram_access_token")),
        instagram_synced_at=row.get("instagram_synced_at"),
        website=row.get("website"),
        following_count=row.get("following_count"),
    )


async def get_creator_by_id(
    creator_id: str,
    *,
    repo: CreatorRepository | None = None,
) -> CreatorResponse | None:
    repo = repo or CreatorRepository()
    row = await repo.get_by_id(creator_id)

    if not row:
        return None

    return _row_to_creator_response(row)


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
    rows, total = await repo.list_filtered(
        search=search,
        niche=niche,
        city=city,
        follower_min=follower_min,
        follower_max=follower_max,
        page=page,
        page_size=page_size,
    )

    return {
        "items": [_row_to_creator_response(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _row_to_portfolio_item(row: dict) -> dict:
    return {
        "id": row["id"],
        "creator_id": row["creator_id"],
        "media_url": row["media_url"],
        "post_link": row.get("post_link"),
        "caption": row.get("caption"),
        "media_type": row.get("media_type", "photo"),
        "like_count": row.get("like_count"),
        "comment_count": row.get("comment_count"),
        "created_at": row["created_at"],
    }


async def get_creator_portfolio(
    creator_id: str,
    media_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
    *,
    repo: CreatorRepository | None = None,
) -> dict:
    repo = repo or CreatorRepository()
    rows, total = await repo.list_portfolio(
        creator_id=creator_id,
        media_type=media_type,
        page=page,
        page_size=page_size,
    )

    return {
        "items": [_row_to_portfolio_item(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_creator_stats(
    profile_id: str,
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

    active_count = await repo.count_active_collaborations(creator_id)

    return {
        "active_collaborations_count": active_count,
        "engagement_growth_pct": None,
    }


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
        campaign = row.get("campaigns", {})
        if campaign:
            items.append({
                "id": campaign.get("id"),
                "business_id": campaign.get("business_id"),
                "title": campaign.get("title"),
                "cover_image_url": campaign.get("cover_image_url"),
                "objective": campaign.get("objective"),
                "compensation_type": campaign.get("compensation_type"),
                "cash_amount_min": campaign.get("cash_amount_min"),
                "cash_amount_max": campaign.get("cash_amount_max"),
                "creator_category": campaign.get("creator_category"),
                "location": campaign.get("location"),
                "deadline": campaign.get("deadline"),
                "status": campaign.get("status"),
                "created_at": campaign.get("created_at"),
            })

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
    if other and other["profile_id"] != profile_id:
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

    return _row_to_creator_response(updated)


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
    if not creator or not creator.get("instagram_access_token"):
        raise _not_connected()

    access_token = decrypt_token(creator["instagram_access_token"])
    expires_at = _parse_expiry(creator.get("instagram_token_expires_at"))

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

    return _row_to_creator_response(updated)


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
    if not creator or not creator.get("instagram_access_token"):
        raise _not_connected()

    access_token = decrypt_token(creator["instagram_access_token"])
    media = await instagram_service.fetch_media(access_token)

    if not media:
        return []

    items = instagram_service.build_portfolio_items(creator["id"], media)
    inserted = await repo.insert_portfolio_items(items)
    return [_row_to_portfolio_item(row) for row in inserted]


def _parse_expiry(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)
