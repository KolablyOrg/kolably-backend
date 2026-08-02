"""
Campaign-related Pydantic schemas — request/response models for all campaign endpoints.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import (
    CampaignObjective,
    CampaignStatus,
    CompensationType,
    ContentType,
    Platform,
)

# ── Step 1: Campaign Foundations ──────────────────────

class CampaignCreateRequest(BaseModel):
    """Step 1 — create a draft campaign."""
    title: str
    objective: CampaignObjective
    description: str


# ── Step 2: Deliverables & Offer ──────────────────────

class DeliverableItem(BaseModel):
    platform: Platform
    content_type: ContentType
    quantity: int = Field(..., ge=1)
    description: str | None = None
    required: bool = True


class CampaignDeliverablesRequest(BaseModel):
    """Step 2 — set deliverables and compensation."""
    deliverables: list[DeliverableItem]
    compensation_type: CompensationType
    cash_amount_min: float | None = None
    cash_amount_max: float | None = None
    free_product_description: str | None = None


# ── Step 3: Targeting ─────────────────────────────────

class CampaignTargetingRequest(BaseModel):
    """Step 3 — set creator targeting criteria."""
    creator_category: str
    follower_range_min: int | None = None
    follower_range_max: int | None = None
    min_engagement_rate: float | None = None
    location: str
    max_creators: int = Field(..., ge=1)
    additional_requirements: str | None = None


# ── Step 4: Finalise & Publish ────────────────────────

class CampaignPublishRequest(BaseModel):
    """Step 4 — set cover image and deadline, then publish."""
    cover_image_url: str | None = None
    deadline: datetime | None = None


# ── General Update ──────────────────────────────────────

class CampaignUpdateRequest(BaseModel):
    """Patch any campaign field (owner only)."""
    title: str | None = None
    description: str | None = None
    objective: CampaignObjective | None = None
    cover_image_url: str | None = None
    deliverables: list[DeliverableItem] | None = None
    compensation_type: CompensationType | None = None
    cash_amount_min: float | None = None
    cash_amount_max: float | None = None
    free_product_description: str | None = None
    creator_category: str | None = None
    follower_range_min: int | None = None
    follower_range_max: int | None = None
    min_engagement_rate: float | None = None
    location: str | None = None
    max_creators: int | None = Field(None, ge=1)
    additional_requirements: str | None = None
    deadline: datetime | None = None


# ── Responses ───────────────────────────────────────────

class CampaignResponse(BaseModel):
    """Full campaign detail."""
    id: str
    business_id: str
    title: str
    objective: CampaignObjective
    description: str
    cover_image_url: str | None = None
    deliverables: list[DeliverableItem]
    compensation_type: CompensationType | None = None  # None until Step 2
    cash_amount_min: float | None = None
    cash_amount_max: float | None = None
    free_product_description: str | None = None
    creator_category: str
    follower_range_min: int | None = None
    follower_range_max: int | None = None
    min_engagement_rate: float | None = None
    location: str
    max_creators: int
    additional_requirements: str | None = None
    deadline: datetime | None = None
    status: CampaignStatus
    created_at: datetime
    applicant_count: int | None = None
    accepted_count: int | None = None


class CampaignSummary(BaseModel):
    """Lightweight campaign card for lists."""
    id: str
    business_id: str
    title: str
    cover_image_url: str | None = None
    objective: CampaignObjective
    compensation_type: CompensationType | None = None  # None until Step 2
    cash_amount_min: float | None = None
    cash_amount_max: float | None = None
    creator_category: str
    location: str
    deadline: datetime | None = None
    status: CampaignStatus
    created_at: datetime
    applicant_count: int | None = None
    # Joined from businesses — present on list/search so cards can render brand info
    business_name: str | None = None
    business_logo_url: str | None = None
    is_verified: bool | None = None


class CampaignCategoryResponse(BaseModel):
    """Static category list item."""
    value: str
    label: str


class InviteRequest(BaseModel):
    """Request body for inviting a creator to a campaign."""
    creator_id: str
    message: str | None = None
