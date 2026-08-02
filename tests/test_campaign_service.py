"""
Unit tests for campaign_service — repositories injected as fakes, no Supabase.
"""

import pytest
from fastapi import HTTPException

from app.core.enums import CampaignStatus, UserRole
from app.models.campaign import Campaign
from app.schemas.user import UserInToken
from app.services import campaign_service

CAMPAIGN_ROW = {
    "id": "camp1",
    "business_id": "b1",
    "title": "Summer Campaign",
    "objective": "brand_awareness",
    "description": "Promote the summer menu",
    "cover_image_url": None,
    "deliverables": [],
    "compensation_type": "cash",
    "cash_amount_min": 100.0,
    "cash_amount_max": 200.0,
    "free_product_description": None,
    "creator_category": "food",
    "follower_range_min": None,
    "follower_range_max": None,
    "min_engagement_rate": None,
    "location": "Springfield",
    "max_creators": 5,
    "additional_requirements": None,
    "deadline": None,
    "status": "active",
    "created_at": "2024-01-01T00:00:00+00:00",
}


def _make_campaign(row: dict) -> Campaign:
    return Campaign.from_row(row)


class FakeCampaignRepo:
    def __init__(self, row=None):
        self._row = row if row is not None else dict(CAMPAIGN_ROW)

    async def get_by_id(self, campaign_id: str):
        return Campaign.from_row(self._row) if self._row else None

    async def fetch_application_counts(self, campaign_ids: list[str]):
        return {}


class FakeBusinessRepo:
    def __init__(self, business_id: str | None = "b1"):
        self._business_id = business_id

    async def get_id_by_profile_id(self, profile_id: str):
        return self._business_id


def _business_user(profile_id: str = "p-business") -> UserInToken:
    return UserInToken(
        id=profile_id,
        auth_id="auth-business",
        email="biz@example.com",
        role=UserRole.BUSINESS,
        is_active=True,
    )


def _superadmin_user() -> UserInToken:
    return UserInToken(
        id="p-admin",
        auth_id="auth-admin",
        email="admin@example.com",
        role=UserRole.SUPERADMIN,
        is_active=True,
    )


async def test_get_campaign_active_is_public():
    repo = FakeCampaignRepo(row=dict(CAMPAIGN_ROW))

    result = await campaign_service.get_campaign("camp1", user=None, campaign_repo=repo)

    assert result.id == "camp1"
    assert result.status == CampaignStatus.ACTIVE


async def test_get_campaign_draft_returns_404_without_auth():
    draft_row = dict(CAMPAIGN_ROW)
    draft_row["status"] = "draft"
    repo = FakeCampaignRepo(row=draft_row)

    with pytest.raises(HTTPException) as exc_info:
        await campaign_service.get_campaign("camp1", user=None, campaign_repo=repo)

    assert exc_info.value.status_code == 404


async def test_get_campaign_draft_returns_404_for_non_owner():
    draft_row = dict(CAMPAIGN_ROW)
    draft_row["status"] = "draft"
    repo = FakeCampaignRepo(row=draft_row)
    business_repo = FakeBusinessRepo(business_id="other-biz")

    with pytest.raises(HTTPException) as exc_info:
        await campaign_service.get_campaign(
            "camp1",
            user=_business_user(),
            campaign_repo=repo,
            business_repo=business_repo,
        )

    assert exc_info.value.status_code == 404


async def test_get_campaign_draft_visible_to_owner():
    draft_row = dict(CAMPAIGN_ROW)
    draft_row["status"] = "draft"
    repo = FakeCampaignRepo(row=draft_row)
    business_repo = FakeBusinessRepo(business_id="b1")

    result = await campaign_service.get_campaign(
        "camp1",
        user=_business_user(),
        campaign_repo=repo,
        business_repo=business_repo,
    )

    assert result.id == "camp1"
    assert result.status == CampaignStatus.DRAFT


async def test_get_campaign_draft_visible_to_superadmin():
    draft_row = dict(CAMPAIGN_ROW)
    draft_row["status"] = "draft"
    repo = FakeCampaignRepo(row=draft_row)
    business_repo = FakeBusinessRepo(business_id=None)

    result = await campaign_service.get_campaign(
        "camp1",
        user=_superadmin_user(),
        campaign_repo=repo,
        business_repo=business_repo,
    )

    assert result.id == "camp1"
    assert result.status == CampaignStatus.DRAFT


async def test_get_campaign_closed_is_public():
    closed_row = dict(CAMPAIGN_ROW)
    closed_row["status"] = "closed"
    repo = FakeCampaignRepo(row=closed_row)

    result = await campaign_service.get_campaign("camp1", user=None, campaign_repo=repo)

    assert result.status == CampaignStatus.CLOSED
