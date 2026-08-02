"""
Unit tests for business_service — repositories injected as fakes, no Supabase.
"""

from app.models.business import Business
from app.models.campaign import Campaign
from app.schemas.business import BusinessResponse
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
    "instagram_page": None,
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

    def __init__(self, row=None, rows=(), total=0, business_id="b1", campaigns=()):
        self._row = row
        self._rows = list(rows)
        self._total = total
        self._business_id = business_id
        self._campaigns = list(campaigns)
        self.seen_business_id: str | None = None

    async def get_by_id(self, business_id: str):
        return _make_business(self._row) if self._row else None

    async def list_filtered(self, **kwargs):
        return [_make_business(r) for r in self._rows], self._total

    async def get_id_by_profile_id(self, profile_id: str):
        return self._business_id

    async def list_campaigns(self, business_id: str, **kwargs):
        self.seen_business_id = business_id
        self.seen_status = kwargs.get("status")
        return [_make_campaign(c) for c in self._campaigns], len(self._campaigns)


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

    result = await business_service.list_my_campaigns(profile_id="p1", repo=repo)

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
    )

    assert repo.seen_status == "active"


async def test_list_my_campaigns_includes_draft_with_null_compensation_type():
    draft_row = dict(CAMPAIGN_ROW)
    draft_row["status"] = "draft"
    draft_row["compensation_type"] = None
    repo = FakeBusinessRepo(business_id="b1", campaigns=[draft_row])

    result = await business_service.list_my_campaigns(profile_id="p1", repo=repo)

    assert result["total"] == 1
    assert result["items"][0].status.value == "draft"
    assert result["items"][0].compensation_type is None
