"""
Creator-related Pydantic schemas.
"""

from datetime import datetime

from pydantic import BaseModel


class CreatorBase(BaseModel):
    name: str
    username: str
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
    created_at: datetime
