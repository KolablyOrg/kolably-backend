"""
Application-related Pydantic schemas.
"""

from datetime import datetime

from pydantic import BaseModel

from app.core.enums import ApplicationDirection, ApplicationStatus
from app.schemas.business import BusinessSummary
from app.schemas.campaign import CampaignSummary
from app.schemas.creator import CreatorSummary


class ApplicationCreateRequest(BaseModel):
    campaign_id: str
    message: str | None = None
    instagram_handle: str | None = None
    example_content_url: str | None = None


class ApplicationResponse(BaseModel):
    id: str
    campaign_id: str
    creator_id: str
    direction: ApplicationDirection = ApplicationDirection.CREATOR_APPLIED
    message: str | None = None
    instagram_handle: str | None = None
    example_content_url: str | None = None
    status: ApplicationStatus
    revision_reason: str | None = None
    created_at: datetime
    # Only set on brand invites — drives the "Expires in N days" countdown
    # and is re-checked server-side when the creator accepts.
    expires_at: datetime | None = None


class ApplicationWithCampaign(ApplicationResponse):
    """GET /applications/me/sent"""
    campaign: CampaignSummary
    business: BusinessSummary


class ApplicationWithCreator(ApplicationResponse):
    """GET /campaigns/{id}/applications, GET /businesses/me/applications"""
    creator: CreatorSummary


class ApplicationUpdateRequest(BaseModel):
    """Creator resubmits after revision request."""
    message: str | None = None
    instagram_handle: str | None = None
    example_content_url: str | None = None


class ApplicationRevisionRequest(BaseModel):
    """Business requests revision."""
    reason: str
