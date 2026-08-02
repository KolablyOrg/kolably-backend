"""
Instagram Graph API client (Instagram API with Instagram Login).

Confirmed working against `graph.instagram.com` / `api.instagram.com` —
profile fields, media list, and media insights all return correctly for a
Business account authorized through this flow. No Facebook Page link is
required (unlike the classic Facebook Login for Business product).

All calls use `INSTAGRAM_APP_ID`/`INSTAGRAM_APP_SECRET`. Shared by both the
`/auth/instagram` signup/login flow and the `/creators/me/instagram/*`
connect flow.
"""

from urllib.parse import urlencode

import httpx
from cryptography.fernet import InvalidToken

from app.core.config import settings
from app.core.crypto import decrypt_token, encrypt_token
from app.core.exceptions import ExternalServiceError

_AUTHORIZE_URL = "https://www.instagram.com/oauth/authorize"
_AUTHORIZE_TOKEN_URL = "https://api.instagram.com/oauth/access_token"
_GRAPH_BASE = "https://graph.instagram.com"
_SCOPES = "instagram_business_basic,instagram_business_manage_insights"

_PROFILE_FIELDS = (
    "user_id,username,name,biography,website,account_type,"
    "followers_count,follows_count,media_count,profile_picture_url"
)
_MEDIA_FIELDS = (
    "id,caption,media_type,media_product_type,media_url,thumbnail_url,permalink,"
    "like_count,comments_count,timestamp,children{media_url,thumbnail_url,media_type}"
)
_INSIGHT_METRICS = ["reach", "likes", "comments", "shares", "saved", "total_interactions"]


def build_authorize_url(redirect_uri: str, state: str | None = None) -> str:
    """The `instagram.com/oauth/authorize` URL for the client to redirect to."""
    params = {
        "client_id": settings.INSTAGRAM_APP_ID,
        "redirect_uri": redirect_uri,
        "scope": _SCOPES,
        "response_type": "code",
    }
    if state:
        params["state"] = state
    return f"{_AUTHORIZE_URL}?{urlencode(params)}"


def relay_redirect_uri() -> str:
    """The single, fixed HTTPS redirect_uri every Instagram OAuth flow uses —
    Instagram rejects anything else, so a mobile app's own exp://.../mobile://
    scheme can never be registered with Meta directly. This backend relays
    the result on to the caller's real destination (see `encode_app_redirect`
    / the `/auth/instagram/callback` route)."""
    return f"{settings.PUBLIC_API_BASE_URL}/api/v1/auth/instagram/callback"


def encode_app_redirect(app_redirect_uri: str) -> str:
    """Pack the caller's real (non-https) redirect target into an encrypted
    `state` value — only this backend can produce or read it, so it can't be
    abused as an open redirect by a crafted `state` param."""
    return encrypt_token(app_redirect_uri)


def decode_app_redirect(state: str) -> str | None:
    try:
        return decrypt_token(state)
    except InvalidToken:
        return None


def build_authorize_url_with_relay(app_redirect_uri: str) -> str:
    """Authorize URL using the fixed relay redirect_uri, with the caller's
    real destination packed into `state`."""
    return build_authorize_url(relay_redirect_uri(), state=encode_app_redirect(app_redirect_uri))


def build_profile_prefill(ig_profile: dict, engagement_rate: float | None) -> dict:
    """Shared shape for the `creators` fields populated from an Instagram profile —
    used by both the direct `/auth/instagram` signup and `/creators/me/instagram/connect`.
    """
    return {
        "name": ig_profile.get("name") or ig_profile["username"],
        "bio": ig_profile.get("biography"),
        "website": ig_profile.get("website"),
        "profile_photo_url": ig_profile.get("profile_picture_url"),
        "follower_count": ig_profile.get("followers_count", 0),
        "following_count": ig_profile.get("follows_count"),
        "engagement_rate": engagement_rate,
    }


def get_media_url_or_thumbnail(item: dict) -> str | None:
    """Safely extract a viewable image URL for any media type (photo, video, carousel)."""
    if item.get("media_type") == "CAROUSEL_ALBUM":
        children = item.get("children", {}).get("data", [])
        if children:
            return children[0].get("thumbnail_url") or children[0].get("media_url")

    url = item.get("thumbnail_url") or item.get("media_url")
    if url:
        return url
    return None


def build_portfolio_items(creator_id: str, media: list[dict]) -> list[dict]:
    """Shared shape for mapping fetched IG media into `portfolio_items` rows."""
    return [
        {
            "creator_id": creator_id,
            "media_url": get_media_url_or_thumbnail(item),
            "post_link": item.get("permalink"),
            "media_type": "video" if item.get("media_type") == "VIDEO" else "photo",
            "like_count": item.get("like_count"),
            "comment_count": item.get("comments_count"),
        }
        for item in media
    ]


async def _request(method: str, url: str, **kwargs) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.request(method, url, **kwargs)
    if response.status_code >= 400:
        raise ExternalServiceError(f"Instagram API error ({response.status_code}): {response.text}")
    return response.json()


async def exchange_code_for_token(code: str, redirect_uri: str) -> dict:
    """POST the OAuth `code` for a short-lived access token + Instagram user id."""
    data = {
        "client_id": settings.INSTAGRAM_APP_ID,
        "client_secret": settings.INSTAGRAM_APP_SECRET,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
        "code": code,
    }
    return await _request("POST", _AUTHORIZE_TOKEN_URL, data=data)


async def exchange_for_long_lived_token(short_lived_token: str) -> dict:
    """Exchange a short-lived token for a long-lived one (~60-day expiry)."""
    params = {
        "grant_type": "ig_exchange_token",
        "client_secret": settings.INSTAGRAM_APP_SECRET,
        "access_token": short_lived_token,
    }
    return await _request("GET", f"{_GRAPH_BASE}/access_token", params=params)


async def refresh_long_lived_token(long_lived_token: str) -> dict:
    """Refresh a still-valid long-lived token, resetting its ~60-day expiry."""
    params = {"grant_type": "ig_refresh_token", "access_token": long_lived_token}
    return await _request("GET", f"{_GRAPH_BASE}/refresh_access_token", params=params)


async def fetch_profile(access_token: str) -> dict:
    """Fetch profile fields — followers/following counts, name, bio, website, photo."""
    params = {"fields": _PROFILE_FIELDS, "access_token": access_token}
    return await _request("GET", f"{_GRAPH_BASE}/me", params=params)


async def fetch_media(access_token: str) -> list[dict]:
    """Fetch recent media for portfolio import — includes `media_product_type`
    (FEED/REELS/STORY) for distinguishing Reels from regular posts."""
    params = {"fields": _MEDIA_FIELDS, "access_token": access_token}
    result = await _request("GET", f"{_GRAPH_BASE}/me/media", params=params)
    return result.get("data", [])


async def fetch_media_insights(access_token: str, media_id: str, media_type: str) -> dict:
    """Fetch view/engagement insights for one media item.

    `views` only applies to video content — requesting it for a photo/carousel
    post 400s, so it's added conditionally.
    """
    metrics = list(_INSIGHT_METRICS)
    if media_type != "IMAGE":
        metrics.append("views")

    params = {"metric": ",".join(metrics), "access_token": access_token}
    result = await _request("GET", f"{_GRAPH_BASE}/{media_id}/insights", params=params)
    return {item["name"]: item["values"][0]["value"] for item in result.get("data", [])}


async def calculate_engagement_rate(access_token: str, media: list[dict]) -> float | None:
    """Average (likes + comments) / reach across recent media, as a percentage.

    Same shape as the `avg_engagement_rate` formula already used for business
    dashboards (`business_service.py`). Returns `None` if there's no media to
    average (nothing self-reported to overwrite with).
    """
    if not media:
        return None

    ratios = []
    for item in media:
        insights = await fetch_media_insights(access_token, item["id"], item["media_type"])
        reach = insights.get("reach")
        if reach:
            ratios.append((insights.get("likes", 0) + insights.get("comments", 0)) / reach)

    if not ratios:
        return None
    return round((sum(ratios) / len(ratios)) * 100, 2)
