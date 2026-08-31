"""
Business-related Pydantic schemas.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr

from app.schemas.creator import CreatorSummary

DEFAULT_BUSINESS_NOTIFICATION_PREFERENCES: dict[str, bool] = {
    "new_applications": True,
    "creator_messages": True,
    "payment_alerts": True,
}


class BusinessBase(BaseModel):
    business_name: str | None = None
    city: str | None = None
    category: str | None = None
    description: str | None = None
    address: str | None = None
    logo_url: str | None = None
    instagram_handle: str | None = None
    website: str | None = None


class BusinessResponse(BusinessBase):
    id: str
    user_id: str
    owner_name: str
    created_at: datetime
    is_verified: bool = False
    kyb_status: Literal["unverified", "pending", "verified", "rejected"] = "unverified"
    is_discoverable: bool = True
    notification_preferences: dict[str, Any] = DEFAULT_BUSINESS_NOTIFICATION_PREFERENCES
    # ── Subscription (read-only here) ─────────────────────────────────
    # Exposed now, before any billing UI exists, so that building that UI
    # later needs no backend change. Read-only on purpose: these are
    # written by gateway webhooks and by nothing else — deliberately absent
    # from BusinessUpdateRequest below, so a client can never grant itself
    # a plan by PATCHing its own profile.
    plan: Literal["free", "pro"] = "free"
    subscription_status: Literal["none", "trialing", "active", "past_due", "canceled"] = "none"
    current_period_end: datetime | None = None
    cancel_at_period_end: bool = False
    # The tier actually in force right now, derived from plan +
    # subscription_status (a cancelled 'pro' resolves to 'free'). Clients
    # should gate UI on THIS, never on `plan` alone — see
    # app/core/plans.resolve_plan for why the two can disagree.
    effective_plan: Literal["free", "pro"] = "free"


class SetBusinessPlanRequest(BaseModel):
    """Superadmin action: activate or deactivate a brand's subscription.

    This is how subscriptions work today — payment is taken offline
    (a payment gateway needs GST registration, which isn't in place), so a
    human confirms the money arrived and flips the switch.

    `expires_at` is optional but strongly recommended when activating: it
    is the safety net for a manual process. Without it the subscription
    stays active until someone remembers to turn it off, and unpaid brands
    quietly keep unlimited campaigns. With it, entitlement lapses on its
    own (see plans.resolve_plan) and the worst case is a brand who paid
    having to be re-activated, rather than one who didn't keeping access.
    """

    plan: Literal["free", "pro"]
    expires_at: datetime | None = None
    #: Free-text, for the audit trail — e.g. "Paid ₹X by UPI on 29 Aug, ref 12345".
    note: str | None = None


class BusinessUpdateRequest(BaseModel):
    business_name: str | None = None
    city: str | None = None
    category: str | None = None
    description: str | None = None
    address: str | None = None
    logo_url: str | None = None
    instagram_handle: str | None = None
    website: str | None = None
    notification_preferences: dict[str, Any] | None = None
    is_discoverable: bool | None = None


class BusinessSummary(BaseModel):
    id: str
    business_name: str
    logo_url: str | None = None


class BusinessStatsResponse(BaseModel):
    total_reach: int
    reach_change_pct: float
    avg_engagement_rate: float
    engagement_series: list[float]
    campaigns_posted_count: int
    creators_worked_with_count: int


class CreatorActivityBannerResponse(BaseModel):
    """Backs the home-dashboard 'N creators near you posted recently' banner."""

    count: int
    city: str | None = None
    avg_followers: int = 0
    avg_engagement_rate: float = 0.0


# ── KYB (Know-Your-Business) Verification ──────────────────────────────
class KybSubmitRequest(BaseModel):
    business_type: Literal["company", "individual"]
    legal_entity_name: str
    pan_number: str
    gst_number: str | None = None
    document_url: str


class KybReviewRequest(BaseModel):
    """Admin action on a pending KYB submission."""

    decision: Literal["verified", "rejected"]
    rejection_reason: str | None = None


class KybStatusResponse(BaseModel):
    status: Literal["unverified", "pending", "verified", "rejected"]
    submitted_at: datetime | None = None
    verified_at: datetime | None = None
    rejection_reason: str | None = None


# ── Team members ─────────────────────────────────────────────────────
class TeamMemberResponse(BaseModel):
    id: str
    role: Literal["owner", "editor", "viewer"]
    status: Literal["pending", "active"]
    invited_email: str
    profile_id: str | None = None
    created_at: datetime
    accepted_at: datetime | None = None


class TeamInviteRequest(BaseModel):
    email: EmailStr
    role: Literal["editor", "viewer"]


class TeamRoleUpdateRequest(BaseModel):
    role: Literal["editor", "viewer"]


class ShortlistUpdateRequest(BaseModel):
    tags: list[str] = []
    note: str | None = None


class ShortlistItemResponse(BaseModel):
    id: str
    business_id: str
    creator_id: str
    tags: list[str] = []
    note: str | None = None
    created_at: datetime
    updated_at: datetime
    creator: CreatorSummary | None = None
