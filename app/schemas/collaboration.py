"""
Collaboration-related Pydantic schemas.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import Platform


class ContentSubmissionResponse(BaseModel):
    id: str
    collaboration_id: str
    content_url: str
    platform: Platform
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    synced_at: datetime | None = None
    submitted_at: datetime


class ContentSubmitRequest(BaseModel):
    content_url: str
    platform: Platform
    views: int | None = Field(None, description="Required for non-instagram platforms; ignored for instagram")
    likes: int | None = None
    comments: int | None = None
    notes: str | None = None


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


class CollaborationSummary(BaseModel):
    id: str
    campaign_id: str
    creator_id: str
    business_id: str
    status: str
    created_at: datetime
