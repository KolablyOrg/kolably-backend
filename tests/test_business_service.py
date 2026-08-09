"""
Unit tests for business_service — repositories injected as fakes, no Supabase.
"""

import pytest
from fastapi import HTTPException

from app.core.enums import UserRole
from app.models.business import Business
from app.models.campaign import Campaign
from app.schemas.business import BusinessResponse, BusinessUpdateRequest, KybSubmitRequest
from app.services import business_service

BUSINESS_ROW = {
    "id": "b1",
    "profile_id": "p1",
    "business_name": "Cafe Kolab",
    "owner_name": "Bob",
    "category": "food",
    "city": "Springfield",
    "description": None,
    "address": None,
    "logo_url": None,
    "instagram_handle": None,
    "website": None,
    "created_at": "2024-01-01T00:00:00+00:00",
    "is_verified": False,
}

CAMPAIGN_ROW = {
    "id": "camp1",
    "business_id": "b1",
    "title": "Brunch launch",
    "cover_image_url": None,
    "objective": "brand_awareness",
    "compensation_type": "cash",
    "cash_amount_min": 100.0,
    "cash_amount_max": 200.0,
    "creator_category": "food",
    "location": "Springfield",
    "deadline": None,
    "status": "active",
    "created_at": "2024-01-01T00:00:00+00:00",
    "description": "Test campaign",
}


def _make_business(row: dict) -> Business:
    return Business.from_row(row)


def _make_campaign(row: dict) -> Campaign:
    return Campaign.from_row(row)


class FakeBusinessRepo:
    """Duck-typed stand-in for BusinessRepository."""

    def __init__(
        self,
        row=None,
        rows=(),
        total=0,
        business_id="b1",
        campaigns=(),
        campaign_ids=(),
        collab_ids=(),
        submissions=(),
        distinct_creators_count=0,
    ):
        self._row = row
        self._rows = list(rows)
        self._total = total
        self._business_id = business_id
        self._campaigns = list(campaigns)
        self._campaign_ids = list(campaign_ids)
        self._collab_ids = list(collab_ids)
        self._submissions = list(submissions)
        self._distinct_creators_count = distinct_creators_count
        self.seen_business_id: str | None = None
        self.update_calls: list[tuple[str, dict]] = []

    async def get_by_id(self, business_id: str):
        return _make_business(self._row) if self._row else None

    async def get_campaign_ids(self, business_id: str):
        return self._campaign_ids

    async def get_collab_ids_for_campaigns(self, campaign_ids):
        return self._collab_ids

    async def get_submissions_for_collabs(self, collab_ids):
        return self._submissions

    async def count_distinct_creators(self, business_id: str):
        return self._distinct_creators_count

    async def update_business(self, business_id: str, data: dict):
        self.update_calls.append((business_id, data))
        if self._row is None:
            return None
        self._row = {**self._row, **data}
        return _make_business(self._row)

    async def list_filtered(self, **kwargs):
        return [_make_business(r) for r in self._rows], self._total

    async def get_id_by_profile_id(self, profile_id: str):
        return self._business_id

    async def get_by_profile_id(self, profile_id: str):
        return _make_business(self._row) if self._row else None

    async def update_by_profile_id(self, profile_id: str, data: dict):
        self.update_calls.append((profile_id, data))
        if self._row is None:
            return None
        self._row = {**self._row, **data}
        return _make_business(self._row)

    async def list_campaigns(self, business_id: str, **kwargs):
        self.seen_business_id = business_id
        self.seen_status = kwargs.get("status")
        return [_make_campaign(c) for c in self._campaigns], len(self._campaigns)


class FakeCampaignRepo:
    """Duck-typed stand-in for CampaignRepository — only fetch_application_counts is used here."""

    async def fetch_application_counts(self, campaign_ids):
        return {}


class FakeCreatorRepo:
    """Duck-typed stand-in for CreatorRepository — only list_recently_active_by_city is used here."""

    def __init__(self, creators=()):
        self._creators = list(creators)
        self.seen_city = None
        self.seen_since = None

    async def list_recently_active_by_city(self, city, since_iso):
        self.seen_city = city
        self.seen_since = since_iso
        return self._creators


async def test_get_business_by_id_maps_user_id_from_profile_id():
    """Regression: same joined-profile-id bug as the creator side."""
    repo = FakeBusinessRepo(row=dict(BUSINESS_ROW))

    business = await business_service.get_business_by_id("b1", repo=repo)

    assert isinstance(business, BusinessResponse)
    assert business.user_id == "p1"


async def test_get_business_by_id_returns_none_when_missing():
    repo = FakeBusinessRepo(row=None)
    assert await business_service.get_business_by_id("missing", repo=repo) is None


async def test_list_businesses_uses_same_serialization_as_get():
    repo = FakeBusinessRepo(rows=[dict(BUSINESS_ROW)], total=1)

    result = await business_service.list_businesses(repo=repo)

    item = result["items"][0]
    assert isinstance(item, BusinessResponse)
    assert item.model_dump() == business_service._business_to_response(_make_business(dict(BUSINESS_ROW))).model_dump()


async def test_list_my_campaigns_resolves_business_id_from_profile():
    """Covers the path behind GET /businesses/me/campaigns (previously broken:
    imported a non-existent helper and called it unawaited)."""
    repo = FakeBusinessRepo(business_id="b1", campaigns=[dict(CAMPAIGN_ROW)])

    result = await business_service.list_my_campaigns(profile_id="p1", repo=repo, campaign_repo=FakeCampaignRepo())

    assert repo.seen_business_id == "b1"
    assert result["total"] == 1
    assert result["items"][0].id == "camp1"
    assert result["items"][0].title == "Brunch launch"


async def test_list_business_campaigns_passes_status_filter():
    repo = FakeBusinessRepo(business_id="b1", campaigns=[dict(CAMPAIGN_ROW)])

    await business_service.list_business_campaigns(
        business_id="b1",
        status="active",
        repo=repo,
        campaign_repo=FakeCampaignRepo(),
    )

    assert repo.seen_status == "active"


async def test_list_my_campaigns_includes_draft_with_null_compensation_type():
    draft_row = dict(CAMPAIGN_ROW)
    draft_row["status"] = "draft"
    draft_row["compensation_type"] = None
    repo = FakeBusinessRepo(business_id="b1", campaigns=[draft_row])

    result = await business_service.list_my_campaigns(profile_id="p1", repo=repo, campaign_repo=FakeCampaignRepo())

    assert result["total"] == 1
    assert result["items"][0].status.value == "draft"
    assert result["items"][0].compensation_type is None


# ── Creator-activity banner ─────────────────────────────────────────────
async def test_creator_activity_banner_zero_when_business_has_no_city():
    row = dict(BUSINESS_ROW)
    row["city"] = None
    repo = FakeBusinessRepo(row=row)

    result = await business_service.get_creator_activity_banner(
        profile_id="p1", repo=repo, creator_repo=FakeCreatorRepo(),
    )

    assert result.count == 0
    assert result.city is None


async def test_creator_activity_banner_zero_when_no_one_posted_recently():
    repo = FakeBusinessRepo(row=dict(BUSINESS_ROW))
    creator_repo = FakeCreatorRepo(creators=[])

    result = await business_service.get_creator_activity_banner(
        profile_id="p1", repo=repo, creator_repo=creator_repo,
    )

    assert result.count == 0
    assert result.city == "Springfield"
    assert creator_repo.seen_city == "Springfield"


async def test_creator_activity_banner_averages_matching_creators():
    repo = FakeBusinessRepo(row=dict(BUSINESS_ROW))
    creator_repo = FakeCreatorRepo(creators=[
        {"id": "c1", "follower_count": 10000, "engagement_rate": 4.0},
        {"id": "c2", "follower_count": 20000, "engagement_rate": 6.0},
    ])

    result = await business_service.get_creator_activity_banner(
        profile_id="p1", repo=repo, creator_repo=creator_repo,
    )

    assert result.count == 2
    assert result.avg_followers == 15000
    assert result.avg_engagement_rate == 5.0


# ── Profile update & settings ───────────────────────────────────────────
async def test_update_business_applies_only_provided_fields():
    repo = FakeBusinessRepo(row=dict(BUSINESS_ROW))

    result = await business_service.update_business(
        business_id="b1",
        profile_id="p1",
        role=UserRole.BUSINESS,
        data=BusinessUpdateRequest(instagram_handle="@cafekolab", website="cafekolab.in"),
        repo=repo,
    )

    assert isinstance(result, BusinessResponse)
    assert result.instagram_handle == "@cafekolab"
    assert result.website == "cafekolab.in"
    business_id, update_data = repo.update_calls[0]
    assert business_id == "b1"
    assert update_data == {"instagram_handle": "@cafekolab", "website": "cafekolab.in"}


async def test_update_business_404_when_business_missing():
    repo = FakeBusinessRepo(row=None)

    with pytest.raises(HTTPException) as exc_info:
        await business_service.update_business(
            business_id="missing",
            profile_id="p1",
            role=UserRole.BUSINESS,
            data=BusinessUpdateRequest(business_name="New name"),
            repo=repo,
        )

    assert exc_info.value.status_code == 404


async def test_update_business_403_for_non_owner():
    repo = FakeBusinessRepo(row=dict(BUSINESS_ROW))

    with pytest.raises(HTTPException) as exc_info:
        await business_service.update_business(
            business_id="b1",
            profile_id="someone-else",
            role=UserRole.BUSINESS,
            data=BusinessUpdateRequest(business_name="New name"),
            repo=repo,
        )

    assert exc_info.value.status_code == 403
    assert repo.update_calls == []


async def test_update_business_allowed_for_superadmin():
    repo = FakeBusinessRepo(row=dict(BUSINESS_ROW))

    result = await business_service.update_business(
        business_id="b1",
        profile_id="someone-else",
        role=UserRole.SUPERADMIN,
        data=BusinessUpdateRequest(business_name="New name"),
        repo=repo,
    )

    assert result.business_name == "New name"


async def test_update_business_merges_notification_preferences_partial_patch():
    row = {
        **BUSINESS_ROW,
        "notification_preferences": {
            "new_applications": True,
            "creator_messages": True,
            "payment_alerts": True,
        },
    }
    repo = FakeBusinessRepo(row=row)

    result = await business_service.update_business(
        business_id="b1",
        profile_id="p1",
        role=UserRole.BUSINESS,
        data=BusinessUpdateRequest(notification_preferences={"creator_messages": False}),
        repo=repo,
    )

    assert result.notification_preferences == {
        "new_applications": True,
        "creator_messages": False,
        "payment_alerts": True,
    }


async def test_update_business_empty_payload_returns_current_without_write():
    repo = FakeBusinessRepo(row=dict(BUSINESS_ROW))

    result = await business_service.update_business(
        business_id="b1",
        profile_id="p1",
        role=UserRole.BUSINESS,
        data=BusinessUpdateRequest(),
        repo=repo,
    )

    assert result.business_name == BUSINESS_ROW["business_name"]
    assert repo.update_calls == []


async def test_get_business_stats_includes_campaigns_posted_and_creators_worked_with_counts():
    repo = FakeBusinessRepo(
        business_id="b1",
        campaign_ids=["camp1", "camp2"],
        collab_ids=["collab1"],
        submissions=[{"views": 100, "likes": 5, "comments": 1}],
        distinct_creators_count=3,
    )

    result = await business_service.get_business_stats(profile_id="p1", repo=repo)

    assert result.total_reach == 100
    assert result.campaigns_posted_count == 2
    assert result.creators_worked_with_count == 3


# ── KYB (Know-Your-Business) Verification ───────────────────────────────
KYB_SUBMIT_DATA = KybSubmitRequest(
    business_type="company",
    legal_entity_name="Cafe Kolab Pvt Ltd",
    pan_number="abcde1234f",
    gst_number="22AAAAA0000A1Z5",
    document_url="https://example.com/proof.pdf",
)


async def test_submit_kyb_verification_sets_pending_status_and_normalizes_pan():
    repo = FakeBusinessRepo(row=dict(BUSINESS_ROW))

    result = await business_service.submit_kyb_verification(
        profile_id="p1", data=KYB_SUBMIT_DATA, repo=repo
    )

    assert result["status"] == "pending"
    assert result["submitted_at"] is not None
    assert result["verified_at"] is None
    assert result["rejection_reason"] is None

    profile_id, update_data = repo.update_calls[0]
    assert profile_id == "p1"
    assert update_data["pan_number"] == "ABCDE1234F"
    assert update_data["business_type"] == "company"
    assert update_data["legal_entity_name"] == "Cafe Kolab Pvt Ltd"
    assert update_data["gst_number"] == "22AAAAA0000A1Z5"
    assert update_data["business_proof_document_url"] == "https://example.com/proof.pdf"
    assert update_data["kyb_status"] == "pending"


async def test_submit_kyb_verification_404_when_no_business_row():
    repo = FakeBusinessRepo(row=None)

    with pytest.raises(HTTPException) as exc_info:
        await business_service.submit_kyb_verification(
            profile_id="missing", data=KYB_SUBMIT_DATA, repo=repo
        )

    assert exc_info.value.status_code == 404


async def test_get_kyb_status_returns_current_status():
    row = {**BUSINESS_ROW, "kyb_status": "verified", "kyb_verified_at": "2024-02-01T00:00:00+00:00"}
    repo = FakeBusinessRepo(row=row)

    result = await business_service.get_kyb_status(profile_id="p1", repo=repo)

    assert result["status"] == "verified"
    assert result["verified_at"] == "2024-02-01T00:00:00+00:00"


async def test_get_kyb_status_defaults_to_unverified():
    repo = FakeBusinessRepo(row=dict(BUSINESS_ROW))

    result = await business_service.get_kyb_status(profile_id="p1", repo=repo)

    assert result["status"] == "unverified"
    assert result["submitted_at"] is None
    assert result["verified_at"] is None


async def test_get_kyb_status_404_when_no_business_row():
    repo = FakeBusinessRepo(row=None)

    with pytest.raises(HTTPException) as exc_info:
        await business_service.get_kyb_status(profile_id="missing", repo=repo)

    assert exc_info.value.status_code == 404
