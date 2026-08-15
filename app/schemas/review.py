"""
Post-collaboration review schemas.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class ReviewCreateRequest(BaseModel):
    """POST /collaborations/{id}/review — works for both directions; who is
    reviewing whom is derived from the caller's role, never from the body."""

    rating: int = Field(..., ge=1, le=5)
    comment: str | None = Field(None, max_length=1000)


class ReviewResponse(BaseModel):
    id: str
    collaboration_id: str
    reviewer_profile_id: str
    reviewee_profile_id: str
    rating: int
    comment: str | None = None
    created_at: datetime


class RatingSummaryResponse(BaseModel):
    """Aggregate shown on a profile. `average_rating` is null when nobody has
    reviewed yet — distinct from 0, which would read as a bad score."""

    average_rating: float | None = None
    review_count: int = 0
