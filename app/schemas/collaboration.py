"""
Collaboration-related Pydantic schemas.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.core.enums import Platform, SubmissionType


class ContentSubmissionResponse(BaseModel):
    id: str
    collaboration_id: str
    content_url: str
    platform: Platform
    submission_type: SubmissionType = SubmissionType.DRAFT
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    synced_at: datetime | None = None
    submitted_at: datetime
    verification_checks: dict[str, Any] | None = None
    verified_at: datetime | None = None


class ContentSubmitRequest(BaseModel):
    content_url: str
    platform: Platform
    submission_type: SubmissionType = Field(
        SubmissionType.DRAFT,
        description=(
            "'draft' = pre-approval cut for review; 'live' = the published post, "
            "submitted after approval for verification + payout. Defaults to draft "
            "so existing callers are unaffected."
        ),
    )
    views: int | None = Field(None, description="Required for non-instagram platforms; ignored for instagram")
    likes: int | None = None
    comments: int | None = None
    notes: str | None = None


class RevisionNoteItem(BaseModel):
    timestamp: str | None = None
    note: str = Field(..., min_length=1)

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parts = value.split(":")
        if len(parts) not in (2, 3) or not all(part.isdigit() for part in parts):
            raise ValueError("Timestamp must use M:SS or H:MM:SS format")
        seconds = int(parts[-1])
        minutes = int(parts[-2])
        if seconds > 59 or (len(parts) == 3 and minutes > 59):
            raise ValueError("Timestamp contains an invalid minute or second")
        return value


class RequestRevisionRequest(BaseModel):
    notes: list[RevisionNoteItem] = Field(default_factory=list)
    overall_note: str | None = None


class RevisionHistoryResponse(BaseModel):
    id: str
    collaboration_id: str
    revision_number: int
    requested_by: str
    notes: list[RevisionNoteItem] = []
    overall_note: str | None = None
    created_at: datetime


class CollaborationCampaignInfo(BaseModel):
    """Joined campaign fields the mobile collab screens render — deliverables,
    payout, and deadlines all live on the campaign, not the collaboration."""
    title: str
    deliverables: list[dict] = []
    deadline: datetime | None = None
    content_due_at: datetime | None = None
    compensation_type: str | None = None
    cash_amount_min: float | None = None
    cash_amount_max: float | None = None
    free_product_description: str | None = None


class CollaborationBusinessInfo(BaseModel):
    id: str
    business_name: str
    logo_url: str | None = None
    gst_number: str | None = None


class CollaborationResponse(BaseModel):
    id: str
    campaign_id: str
    creator_id: str
    business_id: str
    status: str
    content_submissions: list[ContentSubmissionResponse] = []
    affiliate_url: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    revision_notes: list[RevisionNoteItem] = []
    revision_overall_note: str | None = None
    revision_rounds: int = 0
    revision_limit: int = 1
    revision_history: list[RevisionHistoryResponse] = []
    payment_confirmed_at: datetime | None = None
    payment_confirmed_by: str | None = None
    # Joined so mobile can render brand/campaign context without a second
    # round trip — previously absent entirely, which left collab-detail.tsx
    # and collab-submit.tsx rendering blank brand name/logo/payout/deadline.
    campaign_title: str | None = None
    business_name: str | None = None
    brand_logo: str | None = None
    campaign: CollaborationCampaignInfo | None = None
    business: CollaborationBusinessInfo | None = None


class CollaborationSummary(BaseModel):
    id: str
    campaign_id: str
    creator_id: str
    business_id: str
    status: str
    created_at: datetime
