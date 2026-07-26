"""
Business-related Pydantic schemas.
"""

from datetime import datetime

from pydantic import BaseModel


class BusinessBase(BaseModel):
    business_name: str
    city: str
    category: str
    description: str | None = None
    address: str | None = None
    logo_url: str | None = None
    instagram_page: str | None = None
    website: str | None = None


class BusinessResponse(BusinessBase):
    id: str
    user_id: str
    owner_name: str
    created_at: datetime
    is_verified: bool = False


class BusinessUpdateRequest(BaseModel):
    business_name: str | None = None
    city: str | None = None
    category: str | None = None
    description: str | None = None
    address: str | None = None
    logo_url: str | None = None
    instagram_page: str | None = None
    website: str | None = None


class BusinessSummary(BaseModel):
    id: str
    business_name: str
    logo_url: str | None = None


class BusinessStatsResponse(BaseModel):
    total_reach: int
    reach_change_pct: float
    avg_engagement_rate: float
    engagement_series: list[float]
