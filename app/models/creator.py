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
    # Video-only — Instagram doesn't report views for photos (see
    # instagram_service.fetch_media_insights).
    view_count: int | None = None
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
            view_count=row.get("view_count"),
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
            "view_count": self.view_count,
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
    youtube_handle: str | None = None
    instagram_user_id: str | None = None
    instagram_access_token: str | None = None  # Encrypted at rest
    instagram_token_expires_at: datetime | None = None
    instagram_synced_at: datetime | None = None
    instagram_connected: bool = False
    website: str | None = None
    following_count: int | None = None
    portfolio: list[PortfolioItem] = field(default_factory=list)
    # ── Settings fields (added via migration 20260802) ───────────────
    categories: list[str] = field(default_factory=list)
    rate_per_reel: int | None = None
    rate_per_story: int | None = None
    show_rate_card: bool = False
    # ── Compensation preference (added via migration 20260812) ───────
    open_to: list[str] = field(default_factory=list)
    is_discoverable: bool = True
    notification_preferences: dict[str, Any] = field(
        default_factory=lambda: {
            "campaign_alerts": True,
            "brand_messages": True,
            "payout_updates": True,
        }
    )
    # ── Payout & Identity fields (added via migration 20260802) ──────
    payout_method_type: str | None = None
    account_holder_name: str | None = None
    account_number_last4: str | None = None
    ifsc_code: str | None = None
    bank_name: str | None = None
    upi_id: str | None = None
    pan_number: str | None = None
    has_gst: bool = False
    gst_number: str | None = None
    payout_verified: bool = False
    identity_status: str = "unverified"
    identity_document_url: str | None = None
    identity_submitted_at: datetime | None = None
    identity_verified_at: datetime | None = None

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
            youtube_handle=row.get("youtube_handle"),
            instagram_user_id=row.get("instagram_user_id"),
            instagram_access_token=row.get("instagram_access_token"),
            instagram_token_expires_at=row.get("instagram_token_expires_at"),
            instagram_synced_at=row.get("instagram_synced_at"),
            instagram_connected=bool(row.get("instagram_user_id")),
            website=row.get("website"),
            following_count=row.get("following_count"),
            categories=row.get("categories") or [],
            rate_per_reel=row.get("rate_per_reel"),
            rate_per_story=row.get("rate_per_story"),
            show_rate_card=bool(row.get("show_rate_card", False)),
            open_to=row.get("open_to") or [],
            is_discoverable=bool(row.get("is_discoverable", True)),
            notification_preferences=row.get(
                "notification_preferences",
                {"campaign_alerts": True, "brand_messages": True, "payout_updates": True},
            ),
            payout_method_type=row.get("payout_method_type"),
            account_holder_name=row.get("account_holder_name"),
            account_number_last4=row.get("account_number_last4"),
            ifsc_code=row.get("ifsc_code"),
            bank_name=row.get("bank_name"),
            upi_id=row.get("upi_id"),
            pan_number=row.get("pan_number"),
            has_gst=bool(row.get("has_gst", False)),
            gst_number=row.get("gst_number"),
            payout_verified=bool(row.get("payout_verified", False)),
            identity_status=row.get("identity_status", "unverified"),
            identity_document_url=row.get("identity_document_url"),
            identity_submitted_at=row.get("identity_submitted_at"),
            identity_verified_at=row.get("identity_verified_at"),
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
            "youtube_handle": self.youtube_handle,
            "instagram_user_id": self.instagram_user_id,
            "instagram_access_token": self.instagram_access_token,
            "instagram_token_expires_at": self.instagram_token_expires_at,
            "instagram_synced_at": self.instagram_synced_at,
            "website": self.website,
            "following_count": self.following_count,
            "categories": self.categories,
            "rate_per_reel": self.rate_per_reel,
            "rate_per_story": self.rate_per_story,
            "show_rate_card": self.show_rate_card,
            "open_to": self.open_to,
            "is_discoverable": self.is_discoverable,
            "notification_preferences": self.notification_preferences,
            "payout_method_type": self.payout_method_type,
            "account_holder_name": self.account_holder_name,
            "account_number_last4": self.account_number_last4,
            "ifsc_code": self.ifsc_code,
            "bank_name": self.bank_name,
            "upi_id": self.upi_id,
            "pan_number": self.pan_number,
            "has_gst": self.has_gst,
            "gst_number": self.gst_number,
            "payout_verified": self.payout_verified,
            "identity_status": self.identity_status,
            "identity_document_url": self.identity_document_url,
            "identity_submitted_at": self.identity_submitted_at,
            "identity_verified_at": self.identity_verified_at,
        }

    def to_public_row(self) -> dict[str, Any]:
        """Convert to dict for public responses (excludes sensitive fields).

        `instagram_handle` is a free-text field self-reported at signup, so
        its presence alone doesn't mean Instagram is actually connected —
        callers need the real signal before we strip `instagram_user_id`.
        """
        row = self.to_row()
        row["instagram_connected"] = bool(row.get("instagram_user_id"))
        row.pop("instagram_access_token", None)
        row.pop("instagram_token_expires_at", None)
        row.pop("instagram_user_id", None)
        row.pop("profile_id", None)
        return row
