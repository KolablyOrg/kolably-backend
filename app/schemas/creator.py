"""
Creator-related Pydantic schemas.
"""

from datetime import datetime
from typing import Any, Literal

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
    youtube_handle: str | None = None
    instagram_connected: bool = False
    instagram_synced_at: datetime | None = None
    website: str | None = None
    following_count: int | None = None
    # ── Settings fields ──────────────────────────────────────────
    categories: list[str] = []
    rate_per_reel: int | None = None
    rate_per_story: int | None = None
    show_rate_card: bool = False
    open_to: list[str] = []
    is_discoverable: bool = True
    notification_preferences: dict[str, Any] = {
        "campaign_alerts": True,
        "brand_messages": True,
        "payout_updates": True,
    }
    # ── Payout & Identity summary ────────────────────────────────
    payout_method_type: Literal["bank", "upi"] | None = None
    account_number_last4: str | None = None
    bank_name: str | None = None
    upi_id: str | None = None
    payout_verified: bool = False
    identity_status: Literal["unverified", "pending", "verified", "rejected"] = "unverified"


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
    # ── Settings fields ──────────────────────────────────────────
    categories: list[str] | None = None
    rate_per_reel: int | None = Field(None, ge=0)
    rate_per_story: int | None = Field(None, ge=0)
    show_rate_card: bool | None = None
    is_discoverable: bool | None = None
    notification_preferences: dict[str, Any] | None = None


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
    due_this_week_count: int = 0
    pending_invoices_amount: float = 0.0
    engagement_growth: str | None = None
    followers_growth: str | None = None
    views_growth: str | None = None
    engagement_rate: float | None = None
    total_views: int | None = None


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


# ── Payout & Tax Setup ──────────────────────────────────
class PayoutSetupRequest(BaseModel):
    method: Literal["bank", "upi"]
    # Bank fields
    account_name: str | None = None
    account_number: str | None = None
    ifsc_code: str | None = None
    bank_name: str | None = None
    # UPI field
    upi_id: str | None = None
    # Tax fields
    pan_number: str | None = Field(None, min_length=10, max_length=10)
    has_gst: bool = False
    gst_number: str | None = None


class PayoutResponse(BaseModel):
    payout_method_type: Literal["bank", "upi"] | None = None
    account_holder_name: str | None = None
    account_number_last4: str | None = None
    ifsc_code: str | None = None
    bank_name: str | None = None
    upi_id: str | None = None
    pan_number: str | None = None
    has_gst: bool = False
    gst_number: str | None = None
    payout_verified: bool = False


# ── Identity Verification ──────────────────────────────
class IdentitySubmitRequest(BaseModel):
    pan_number: str = Field(..., min_length=10, max_length=10)
    document_url: str | None = None


class IdentityStatusResponse(BaseModel):
    status: Literal["unverified", "pending", "verified", "rejected"]
    submitted_at: datetime | None = None
    verified_at: datetime | None = None
    rejection_reason: str | None = None


class BulkDeletePortfolioRequest(BaseModel):
    item_ids: list[str]
