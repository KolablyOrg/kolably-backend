"""
Creator domain models.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class PortfolioItem:
    """Portfolio item domain model."""
    id: str
    creator_id: str
    title: str | None = None
    media_url: str = ""
    post_link: str | None = None
    media_type: str = "photo"
    like_count: int | None = None
    comment_count: int | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "PortfolioItem":
        return cls(
            id=row["id"],
            creator_id=row["creator_id"],
            title=row.get("title"),
            media_url=row["media_url"],
            post_link=row.get("post_link"),
            media_type=row.get("media_type", "photo"),
            like_count=row.get("like_count"),
            comment_count=row.get("comment_count"),
            created_at=row["created_at"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "creator_id": self.creator_id,
            "title": self.title,
            "media_url": self.media_url,
            "post_link": self.post_link,
            "media_type": self.media_type,
            "like_count": self.like_count,
            "comment_count": self.comment_count,
            "created_at": self.created_at,
        }


@dataclass
class Creator:
    """Creator domain model — internal representation."""
    id: str
    profile_id: str
    name: str
    username: str | None = None
    city: str | None = None
    niche: str | None = None
    follower_count: int | None = None
    bio: str | None = None
    instagram_handle: str | None = None
    engagement_rate: float | None = None
    profile_photo_url: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    tiktok_handle: str | None = None
    instagram_user_id: str | None = None
    instagram_access_token: str | None = None  # Encrypted at rest
    instagram_token_expires_at: datetime | None = None
    instagram_synced_at: datetime | None = None
    instagram_connected: bool = False
    website: str | None = None
    following_count: int | None = None
    portfolio: list[PortfolioItem] = field(default_factory=list)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Creator":
        return cls(
            id=row["id"],
            profile_id=row["profile_id"],
            name=row["name"],
            username=row.get("username"),
            city=row.get("city"),
            niche=row.get("niche"),
            follower_count=row.get("follower_count"),
            bio=row.get("bio"),
            instagram_handle=row.get("instagram_handle"),
            engagement_rate=row.get("engagement_rate"),
            profile_photo_url=row.get("profile_photo_url"),
            created_at=row["created_at"],
            tiktok_handle=row.get("tiktok_handle"),
            instagram_user_id=row.get("instagram_user_id"),
            instagram_access_token=row.get("instagram_access_token"),
            instagram_token_expires_at=row.get("instagram_token_expires_at"),
            instagram_synced_at=row.get("instagram_synced_at"),
            instagram_connected=bool(row.get("instagram_user_id")),
            website=row.get("website"),
            following_count=row.get("following_count"),
        )

    def to_row(self) -> dict[str, Any]:
        """Convert to dict for database insert/update (excludes sensitive fields)."""
        return {
            "id": self.id,
            "profile_id": self.profile_id,
            "name": self.name,
            "username": self.username,
            "city": self.city,
            "niche": self.niche,
            "follower_count": self.follower_count,
            "bio": self.bio,
            "instagram_handle": self.instagram_handle,
            "engagement_rate": self.engagement_rate,
            "profile_photo_url": self.profile_photo_url,
            "created_at": self.created_at,
            "tiktok_handle": self.tiktok_handle,
            "instagram_user_id": self.instagram_user_id,
            "instagram_access_token": self.instagram_access_token,
            "instagram_token_expires_at": self.instagram_token_expires_at,
            "instagram_synced_at": self.instagram_synced_at,
            "website": self.website,
            "following_count": self.following_count,
        }

    def to_public_row(self) -> dict[str, Any]:
        """Convert to dict for public responses (excludes sensitive fields)."""
        row = self.to_row()
        row.pop("instagram_access_token", None)
        row.pop("instagram_token_expires_at", None)
        row.pop("instagram_user_id", None)
        row.pop("profile_id", None)
        return row
