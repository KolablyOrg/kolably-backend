"""
Creator-related Pydantic schemas.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CreatorBase(BaseModel):
    name: str
    username: str | None = None
    city: str
    niche: str
    follower_count: int
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
    city: str | None = None
    niche: str | None = None
    follower_count: int | None = None
    bio: str | None = None
    instagram_handle: str | None = None
    profile_photo_url: str | None = None


class CreatorSummary(BaseModel):
    """Minimal creator info for nested responses."""
    id: str
    name: str
    profile_photo_url: str | None = None
    follower_count: int | None = None
    niche: str | None = None


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
