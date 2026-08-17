import logging
from datetime import UTC, datetime, timedelta
from typing import Any

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

logger = logging.getLogger(__name__)

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
        youtube_handle=creator.youtube_handle,
        instagram_connected=creator.instagram_connected,
        instagram_synced_at=creator.instagram_synced_at,
        website=creator.website,
        following_count=creator.following_count,
        # Settings fields
        categories=creator.categories or [],
        rate_per_reel=creator.rate_per_reel,
        rate_per_story=creator.rate_per_story,
        show_rate_card=creator.show_rate_card,
        open_to=creator.open_to or [],
        is_discoverable=creator.is_discoverable,
        notification_preferences=creator.notification_preferences or {
            "campaign_alerts": True,
            "brand_messages": True,
            "payout_updates": True,
        },
        payout_method_type=creator.payout_method_type,
        account_number_last4=creator.account_number_last4,
        bank_name=creator.bank_name,
        upi_id=creator.upi_id,
        payout_verified=creator.payout_verified,
        identity_status=creator.identity_status or "unverified",
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
    city: list[str] | None = None,
    follower_min: int | None = None,
    follower_max: int | None = None,
    engagement_min: float | None = None,
    verified_only: bool = False,
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
        engagement_min=engagement_min,
        verified_only=verified_only,
        page=page,
        page_size=page_size,
    )

    return {
        "items": [_creator_to_response(c) for c in creators],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_locations(
    *,
    repo: CreatorRepository | None = None,
) -> dict:
    """Distinct cities from discoverable creators (mirrors campaign locations)."""
    repo = repo or CreatorRepository()
    locations = await repo.get_locations()
    return {
        "items": locations,
        "total": len(locations),
        "page": 1,
        "page_size": len(locations),
    }


async def get_niches(
    *,
    repo: CreatorRepository | None = None,
) -> dict:
    """Distinct niches from discoverable creators."""
    repo = repo or CreatorRepository()
    niches = await repo.get_niches()
    return {
        "items": niches,
        "total": len(niches),
        "page": 1,
        "page_size": len(niches),
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
    (non-None) fields are written; Instagram-owned fields (instagram_handle,
    follower_count, website, following_count, engagement stats) are not
    updatable here at all — `CreatorUpdateRequest` doesn't even define them
    as fields, so they can never be self-reported, connected or not. They
    only ever come from connect_instagram/sync_instagram."""
    repo = repo or CreatorRepository()
    creator = await repo.get_by_id(creator_id)
    if not creator:
        creator = await repo.get_by_profile_id(creator_id)
    _ensure_creator_access(creator, profile_id, role)

    update_data = data.model_dump(exclude_none=True)

    # ── notification_preferences: merge incoming keys onto existing ones
    # so a client sending {campaign_alerts: false} doesn't wipe the others.
    if "notification_preferences" in update_data and creator.notification_preferences:
        merged = dict(creator.notification_preferences)  # start with current
        merged.update(update_data["notification_preferences"])  # apply partial patch
        update_data["notification_preferences"] = merged

    if not update_data:
        return _creator_to_response(creator)

    updated = await repo.update_creator(creator.id, update_data)
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


async def bulk_delete_portfolio_items(
    creator_id: str,
    item_ids: list[str],
    profile_id: str,
    role: UserRole,
    *,
    repo: CreatorRepository | None = None,
) -> None:
    repo = repo or CreatorRepository()
    creator = await repo.get_by_id(creator_id)
    _ensure_creator_access(creator, profile_id, role)

    if not item_ids:
        return

    await repo.bulk_delete_portfolio_items(item_ids, creator_id)


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

    # Auto-repair legacy items that have raw .mp4 URLs instead of thumbnails
    broken = [item for item in items if item.media_url and ".mp4" in item.media_url]
    if broken:
        try:
            creator = await repo.get_by_id(creator_id)
            if creator and creator.instagram_access_token:
                access_token = decrypt_token(creator.instagram_access_token)
                ig_media = await instagram_service.fetch_media(access_token)
                # Build a lookup: permalink -> thumbnail_url
                permalink_to_thumb: dict[str, str] = {}
                for m in ig_media:
                    plink = m.get("permalink")
                    thumb = instagram_service.get_media_url_or_thumbnail(m)
                    if plink and thumb and ".mp4" not in thumb:
                        permalink_to_thumb[plink] = thumb

                for item in broken:
                    new_url = permalink_to_thumb.get(item.post_link) if item.post_link else None
                    if new_url:
                        await repo.update_portfolio_item(str(item.id), {"media_url": new_url})
                        item.media_url = new_url
        except Exception:
            # Best-effort repair; don't block portfolio response.
            logger.exception("Portfolio thumbnail repair failed for creator_id=%s", creator_id)

    return {
        "items": [_portfolio_item_to_response(item) for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_creator_stats(
    profile_id: str,
    days: int = 7,
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

    creator = await repo.get_by_id(creator_id)
    active_count = await repo.count_active_collaborations(creator_id)
    due_this_week_count = await repo.count_collaborations_due_this_week(creator_id)
    pending_invoices_amount = await repo.sum_pending_invoice_amount(creator_id)

    # 1. Fetch historical stats
    history = await repo.get_historical_stats(creator_id, days_ago=days)

    def calculate_growth(current: int | float | None, past: int | float | None) -> str:
        if current is None or past is None or past == 0:
            return f"0% vs last {days} days"

        diff = current - past
        pct = (diff / past) * 100
        sign = "↗" if diff > 0 else "↘" if diff < 0 else ""
        return f"{sign} {abs(round(pct, 1))}% vs last {days} days".strip()

    if history and creator:
        engagement_growth = calculate_growth(creator.engagement_rate, history.get("engagement_rate"))
        followers_growth = calculate_growth(creator.follower_count, history.get("follower_count"))
        views_growth = calculate_growth(getattr(creator, "views_count", 0), history.get("views_count"))
    else:
        # Fallback if no history is recorded yet
        engagement_growth = f"0% vs last {days} days"
        followers_growth = f"0% vs last {days} days"
        views_growth = f"0% vs last {days} days"

    return CreatorStatsResponse(
        active_collaborations_count=active_count,
        due_this_week_count=due_this_week_count,
        pending_invoices_amount=pending_invoices_amount,
        engagement_growth=engagement_growth,
        followers_growth=followers_growth,
        views_growth=views_growth,
        engagement_rate=creator.engagement_rate if creator else 0,
        total_views=getattr(creator, "views_count", 0) if creator else 0,
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
    """`redirect_uri` here is where the *client* wants the flow to end up
    (its own exp://.../mobile://... scheme) — Instagram itself only ever
    sees this backend's fixed HTTPS relay URL (see `build_authorize_url_with_relay`)."""
    return {"url": instagram_service.build_authorize_url_with_relay(redirect_uri)}


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

    `redirect_uri` is accepted for API compatibility but unused: Instagram's
    token endpoint requires the exact redirect_uri used at the authorize
    step, which was always the fixed relay URL, never the client's own.
    """
    repo = repo or CreatorRepository()
    creator = await repo.get_by_profile_id(profile_id)
    if not creator:
        raise _no_creator_profile()

    short_lived = await instagram_service.exchange_code_for_token(
        code, instagram_service.relay_redirect_uri()
    )
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


async def _refresh_instagram_stats(creator: Creator, *, repo: CreatorRepository) -> Creator:
    """Core Instagram re-fetch (follower/following count, photo, engagement
    rate) shared by the single-creator `sync_instagram` endpoint and the
    daily batch job (`refresh_all_instagram_stats`). name/bio/website stay
    as connect-time pre-filled them, matching the connect-once/sync-stats-
    only split in API_REQUIREMENTS.md §2.

    Also proactively refreshes the long-lived token if it's close to
    expiring (<10 days left), so a creator who never revisits doesn't
    silently lose their connection at the 60-day mark.

    Raises whatever the underlying Instagram API call raises — callers that
    process many creators in a loop (the batch job) are expected to catch
    per-creator so one bad token doesn't block everyone else.
    """
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

    updated = await repo.update_by_profile_id(creator.profile_id, {
        "follower_count": ig_profile.get("followers_count"),
        "following_count": ig_profile.get("follows_count"),
        "profile_photo_url": ig_profile.get("profile_picture_url"),
        "engagement_rate": engagement_rate,
        "instagram_access_token": encrypt_token(access_token),
        "instagram_token_expires_at": expires_at.isoformat(),
        "instagram_synced_at": datetime.now(UTC).isoformat(),
    })
    if updated is None:
        raise _not_connected()
    return updated


async def sync_instagram(
    profile_id: str,
    *,
    repo: CreatorRepository | None = None,
) -> CreatorResponse:
    """Re-fetch the stats subset only (follower/following count, photo,
    engagement rate) for the current creator — see `_refresh_instagram_stats`."""
    repo = repo or CreatorRepository()
    creator = await repo.get_by_profile_id(profile_id)
    if not creator or not creator.instagram_access_token:
        raise _not_connected()

    updated = await _refresh_instagram_stats(creator, repo=repo)
    return _creator_to_response(updated)


async def refresh_all_instagram_stats(*, repo: CreatorRepository | None = None) -> dict:
    """Daily batch job: re-fetch live Instagram stats for every connected
    creator, then snapshot everyone's current numbers into
    `creator_stats_history` for growth tracking.

    This is what actually keeps `engagement_rate`/`follower_count` current —
    previously the only way to refresh them was a creator manually
    (re)connecting or the app's own best-effort background sync, and the
    only piece of write-side "history" tracking (`creator_repo.
    snapshot_all_creators`) was never actually invoked by anything (no
    cron/systemd/CI schedule called `/cron/snapshot-stats`), so day-over-day
    growth badges always read "0% vs last N days". See `app/core/scheduler.py`
    for what actually calls this on a schedule now.

    Per-creator failures (expired/revoked token, a transient Instagram API
    error, ...) are caught and skipped so one broken connection never blocks
    the rest of the batch.
    """
    repo = repo or CreatorRepository()
    creators = await repo.list_instagram_connected()

    refreshed = 0
    failed = 0
    for creator in creators:
        try:
            await _refresh_instagram_stats(creator, repo=repo)
            refreshed += 1
        except Exception:
            logger.exception("Instagram stats refresh failed for creator_id=%s", creator.id)
            failed += 1

    await repo.snapshot_all_creators()

    return {"total": len(creators), "refreshed": refreshed, "failed": failed}


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


async def preview_instagram_media(
    profile_id: str,
    *,
    repo: CreatorRepository | None = None,
) -> list[dict]:
    """Fetch recent Instagram media without importing it, so the creator can
    pick which posts/reels to add to their portfolio."""
    repo = repo or CreatorRepository()
    creator = await repo.get_by_profile_id(profile_id)
    if not creator or not creator.instagram_access_token:
        raise _not_connected()

    access_token = decrypt_token(creator.instagram_access_token)
    media = await instagram_service.fetch_media(access_token)

    return [
        {
            "id": str(item["id"]),
            "media_url": instagram_service.get_media_url_or_thumbnail(item),
            "permalink": item.get("permalink"),
            "media_type": "video" if item.get("media_type") == "VIDEO" else "photo",
            "like_count": item.get("like_count"),
            "comment_count": item.get("comments_count"),
        }
        for item in media
        if instagram_service.get_media_url_or_thumbnail(item)
    ]


async def import_instagram_portfolio(
    profile_id: str,
    media_ids: list[str] | None = None,
    *,
    repo: CreatorRepository | None = None,
) -> list[dict]:
    """Pull selected (or all recent) Instagram media into the portfolio.

    Upserts by `post_link` (the Instagram permalink, stable per post) rather
    than always inserting: re-selecting a post that's already in the
    portfolio refreshes its stored media_url/like_count/comment_count in
    place instead of creating a duplicate row. This is also the only way a
    creator can currently fix an older portfolio item stuck with a stale/
    broken media_url (e.g. a reel imported before a thumbnail-extraction fix
    landed) — re-picking it here corrects it, since there's no separate
    portfolio-refresh action.
    """
    repo = repo or CreatorRepository()
    creator = await repo.get_by_profile_id(profile_id)
    if not creator or not creator.instagram_access_token:
        raise _not_connected()

    access_token = decrypt_token(creator.instagram_access_token)
    media = await instagram_service.fetch_media(access_token)

    if media_ids is not None:
        wanted = set(media_ids)
        media = [item for item in media if str(item.get("id")) in wanted]

    if not media:
        return []

    items = instagram_service.build_portfolio_items(creator.id, media)

    post_links = [item["post_link"] for item in items if item.get("post_link")]
    existing_by_link = {
        item.post_link: item
        for item in await repo.get_portfolio_items_by_post_links(creator.id, post_links)
    }

    to_insert = []
    updated = []
    for item in items:
        existing = existing_by_link.get(item.get("post_link"))
        if existing:
            refreshed = await repo.update_portfolio_item(existing.id, {
                "media_url": item["media_url"],
                "like_count": item["like_count"],
                "comment_count": item["comment_count"],
            })
            if refreshed:
                updated.append(refreshed)
        else:
            to_insert.append(item)

    inserted = await repo.insert_portfolio_items(to_insert)
    return [_portfolio_item_to_response(item) for item in [*updated, *inserted]]


def _parse_expiry(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


# ── Payout & Tax Setup Service Methods ─────────────────────────────────
async def save_payout_details(
    profile_id: str,
    data: Any,
    *,
    repo: CreatorRepository | None = None,
) -> dict:
    repo = repo or CreatorRepository()
    creator = await repo.get_by_profile_id(profile_id)
    if not creator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator profile not found",
        )

    update_data: dict[str, Any] = {
        "payout_method_type": data.method,
        # payout_verified intentionally left untouched here. Bank/UPI
        # details are self-reported with no penny-drop/IFSC lookup behind
        # them, so there is nothing to actually verify yet — it stays at
        # its schema default (false) until real verification exists. Do
        # not hardcode this to True; the UI reads it to show a "Verified"
        # badge, and that would be a false claim to both creators and
        # the brands who see it.
        "has_gst": data.has_gst,
    }

    if data.method == "bank":
        if not data.account_number or not data.ifsc_code:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Account number and IFSC code are required for bank payout",
            )
        last4 = data.account_number.strip()[-4:]
        update_data["account_holder_name"] = data.account_name
        update_data["account_number_last4"] = last4
        update_data["ifsc_code"] = data.ifsc_code.upper()
        update_data["bank_name"] = data.bank_name or "HDFC Bank"
    elif data.method == "upi":
        if not data.upi_id or "@" not in data.upi_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Valid UPI ID is required",
            )
        update_data["upi_id"] = data.upi_id.strip()

    if data.pan_number:
        update_data["pan_number"] = data.pan_number.upper().strip()
    if data.has_gst and data.gst_number:
        update_data["gst_number"] = data.gst_number.upper().strip()

    updated = await repo.update_creator(creator.id, update_data)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update payout details",
        )

    return {
        "payout_method_type": updated.payout_method_type,
        "account_holder_name": updated.account_holder_name,
        "account_number_last4": updated.account_number_last4,
        "ifsc_code": updated.ifsc_code,
        "bank_name": updated.bank_name,
        "upi_id": updated.upi_id,
        "pan_number": updated.pan_number,
        "has_gst": updated.has_gst,
        "gst_number": updated.gst_number,
        "payout_verified": updated.payout_verified,
    }


async def get_payout_details(
    profile_id: str,
    *,
    repo: CreatorRepository | None = None,
) -> dict:
    repo = repo or CreatorRepository()
    creator = await repo.get_by_profile_id(profile_id)
    if not creator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator profile not found",
        )

    return {
        "payout_method_type": creator.payout_method_type,
        "account_holder_name": creator.account_holder_name,
        "account_number_last4": creator.account_number_last4,
        "ifsc_code": creator.ifsc_code,
        "bank_name": creator.bank_name,
        "upi_id": creator.upi_id,
        "pan_number": creator.pan_number,
        "has_gst": creator.has_gst,
        "gst_number": creator.gst_number,
        "payout_verified": creator.payout_verified,
    }


# ── Identity Verification Service Methods ──────────────────────────────
async def submit_identity_verification(
    profile_id: str,
    data: Any,
    *,
    repo: CreatorRepository | None = None,
) -> dict:
    repo = repo or CreatorRepository()
    creator = await repo.get_by_profile_id(profile_id)
    if not creator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator profile not found",
        )

    now = datetime.now(UTC)
    update_data = {
        "pan_number": data.pan_number.upper().strip(),
        "identity_status": "pending",
        "identity_document_url": data.document_url,
        "identity_submitted_at": now.isoformat(),
    }

    updated = await repo.update_creator(creator.id, update_data)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit identity verification",
        )

    return {
        "status": updated.identity_status,
        "submitted_at": updated.identity_submitted_at,
        "verified_at": updated.identity_verified_at,
        "rejection_reason": None,
    }


async def get_identity_status(
    profile_id: str,
    *,
    repo: CreatorRepository | None = None,
) -> dict:
    repo = repo or CreatorRepository()
    creator = await repo.get_by_profile_id(profile_id)
    if not creator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator profile not found",
        )

    return {
        "status": creator.identity_status or "unverified",
        "submitted_at": creator.identity_submitted_at,
        "verified_at": creator.identity_verified_at,
        "rejection_reason": None,
    }
