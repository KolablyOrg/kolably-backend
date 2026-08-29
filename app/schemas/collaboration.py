"""
Collaboration-related Pydantic schemas.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.core.enums import DraftReviewStatus, Platform, SubmissionType


class RevisionNoteItem(BaseModel):
    timestamp: str | None = None
    note: str = Field(..., min_length=1)

    @field_validator("timestamp", mode="before")
    @classmethod
    def validate_timestamp(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            value = str(value)
        trimmed = value.strip()
        if not trimmed:
            return None
        normalized = trimmed.replace(".", ":")
        parts = normalized.split(":")
        if len(parts) not in (2, 3) or not all(part.isdigit() for part in parts):
            raise ValueError("Timestamp must use M:SS or H:MM:SS format (e.g. 0:04 or 1:23)")
        if len(parts) == 2:
            minutes, seconds = int(parts[0]), int(parts[1])
            if seconds > 59:
                raise ValueError("Timestamp seconds must be less than 60")
            return f"{minutes}:{seconds:02d}"
        else:
            hours, minutes, seconds = int(parts[0]), int(parts[1]), int(parts[2])
            if minutes > 59 or seconds > 59:
                raise ValueError("Timestamp minutes and seconds must be less than 60")
            return f"{hours}:{minutes:02d}:{seconds:02d}"


class ContentSubmissionResponse(BaseModel):
    id: str
    collaboration_id: str
    content_url: str
    platform: Platform
    content_type: str | None = None
    deliverable_index: int | None = None
    submission_type: SubmissionType = SubmissionType.DRAFT
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    synced_at: datetime | None = None
    submitted_at: datetime
    verification_checks: dict[str, Any] | None = None
    verified_at: datetime | None = None
    draft_status: DraftReviewStatus | None = None
    revision_notes: list[RevisionNoteItem] = []
    revision_overall_note: str | None = None


class ContentSubmitRequest(BaseModel):
    content_url: str
    platform: Platform
    # Which campaign deliverable this submission fulfils. Optional so older
    # clients keep working, but without them the brand can't tell one
    # submission from another beyond its platform.
    content_type: str | None = Field(
        None, description="reel/story/post — mirrors the campaign deliverable's content_type"
    )
    deliverable_index: int | None = Field(
        None,
        ge=0,
        description="Zero-based slot in the expanded deliverable list, so 'reel 2 of 2' is identifiable",
    )
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


class RequestRevisionRequest(BaseModel):
    submission_id: str = Field(
        ...,
        description="The draft submission (deliverable) that needs changes",
    )
    notes: list[RevisionNoteItem] = Field(default_factory=list)
    overall_note: str | None = None


class ApproveSubmissionRequest(BaseModel):
    submission_id: str = Field(
        ...,
        description="The draft submission (deliverable) to approve",
    )


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
    # The brand's *profile* id — what POST /chat/conversations takes as
    # participant_id (`id` above is the business record id, which that
    # endpoint rejects). Without it the client had a `business` object that
    # looked complete but couldn't open a chat, and its own fallback fetch
    # was skipped precisely because this object was present.
    user_id: str | None = None


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
    # Set when the creator confirms they actually received the payment —
    # that confirmation, not payment_confirmed_at, is what completes the
    # collaboration. Clients use the gap between the two to render the
    # "waiting on the creator" / "confirm you were paid" states.
    creator_confirmed_at: datetime | None = None
    # Joined so mobile can render brand/campaign context without a second
    # round trip — previously absent entirely, which left collab-detail.tsx
    # and collab-submit.tsx rendering blank brand name/logo/payout/deadline.
    campaign_title: str | None = None
    business_name: str | None = None
    brand_logo: str | None = None
    campaign: CollaborationCampaignInfo | None = None
    business: CollaborationBusinessInfo | None = None
    # Joined so the brand's Collaborations list can render the creator's name
    # and avatar without firing one getCreator(id) request per row.
    creator_name: str | None = None
    creator_profile_photo_url: str | None = None


class CollaborationSummary(BaseModel):
    id: str
    campaign_id: str
    creator_id: str
    business_id: str
    status: str
    created_at: datetime
