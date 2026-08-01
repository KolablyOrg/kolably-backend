"""
Creator-related Pydantic schemas.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CreatorBase(BaseModel):
    name: str
    username: str | None = None
    # city/niche/follower_count are nullable in Postgres — Instagram-signup
    # creators exist before they complete onboarding.
    city: str | None = None
    niche: str | None = None
    follower_count: int | None = None
    bio: str | None = None
    instagram_handle: str | None = None
    engagement_rate: float | None = None
    profile_photo_url: str | None = None


class CreatorResponse(CreatorBase):
    id: str
    user_id: str
    created_at: datetime
    tiktok_handle: str | None = None
    instagram_connected: bool = False
    instagram_synced_at: datetime | None = None
    website: str | None = None
    following_count: int | None = None


class CreatorUpdateRequest(BaseModel):
    name: str | None = None
    username: str | None = None
    city: str | None = None
    niche: str | None = None
    follower_count: int | None = None
    bio: str | None = None
    instagram_handle: str | None = None
    tiktok_handle: str | None = None
    youtube_handle: str | None = None
    profile_photo_url: str | None = None


class CreatorSummary(BaseModel):
    """Minimal creator info for nested responses."""
    id: str
    name: str
    profile_photo_url: str | None = None
    follower_count: int | None = None
    niche: str | None = None


class PortfolioItemCreateRequest(BaseModel):
    """Manual portfolio addition — `media_url` comes from the client uploading
    directly to Supabase Storage (`portfolio` bucket); the backend only stores
    the URL string. `like_count`/`comment_count` are Instagram-import-only and
    are not accepted here."""
    title: str | None = None
    media_url: str = Field(..., min_length=1)
    post_link: str | None = None
    media_type: Literal["photo", "video"] = "photo"


class PortfolioItemResponse(BaseModel):
    id: str
    creator_id: str
    title: str | None = None
    media_url: str
    post_link: str | None = None
    media_type: Literal["photo", "video"] = "photo"
    like_count: int | None = None
    comment_count: int | None = None
    created_at: datetime


class CreatorStatsResponse(BaseModel):
    active_collaborations_count: int
    engagement_growth_pct: float | None = None


# ── Instagram connection ──────────────────────────────
class InstagramAuthUrlResponse(BaseModel):
    url: str


class InstagramConnectRequest(BaseModel):
    code: str = Field(..., min_length=1)
    redirect_uri: str = Field(..., min_length=1)


class InstagramMediaPreviewItem(BaseModel):
    """One item from the creator's recent Instagram media, fetched but not
    yet imported into their portfolio — lets them pick which ones to add."""
    id: str
    media_url: str
    permalink: str | None = None
    media_type: Literal["photo", "video"] = "photo"
    like_count: int | None = None
    comment_count: int | None = None


class InstagramImportRequest(BaseModel):
    """`media_ids` selects specific previewed items to import; omitted/None
    imports everything (back-compat with the original bulk-import call)."""
    media_ids: list[str] | None = None
