"""
Unit tests for creator_service — repositories injected as fakes, no Supabase.
"""

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.enums import UserRole
from app.models.campaign import Campaign
from app.models.creator import Creator, PortfolioItem
from app.schemas.creator import (
    CreatorResponse,
    CreatorUpdateRequest,
    PayoutSetupRequest,
    PortfolioItemCreateRequest,
)
from app.services import creator_service

CREATOR_ROW = {
    "id": "c1",
    "profile_id": "p1",
    "name": "Alice",
    "username": "alice",
    "profile_photo_url": None,
    "niche": "food",
    "city": "Springfield",
    "follower_count": 1000,
    "engagement_rate": 3.5,
    "bio": "hello",
    "instagram_handle": "@alice",
    "created_at": "2024-01-01T00:00:00+00:00",
    "tiktok_handle": None,
    "instagram_user_id": "ig-user",
    "instagram_access_token": "secret-token",
    "instagram_synced_at": None,
}

CAMPAIGN_ROW = {
    "id": "camp1",
    "business_id": "b1",
    "title": "Summer Campaign",
    "objective": "brand_awareness",
    "description": "Promote the summer menu",
    "cover_image_url": None,
    "deliverables": [
        {"platform": "instagram", "content_type": "post", "quantity": 1, "description": None, "required": True}
    ],
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

PORTFOLIO_ITEM_ROW = {
    "id": "pi1",
    "creator_id": "c1",
    "title": "Spring shoot",
    "media_url": "https://storage.example.com/portfolio/1.jpg",
    "post_link": None,
    "media_type": "photo",
    "like_count": None,
    "comment_count": None,
    "created_at": "2024-01-01T00:00:00+00:00",
}


def _make_creator(row: dict) -> Creator:
    return Creator.from_row(row)


def _make_portfolio_item(row: dict) -> PortfolioItem:
    return PortfolioItem.from_row(row)


class FakeCreatorRepo:
    """Duck-typed stand-in for CreatorRepository."""

    def __init__(
        self,
        row=None,
        rows=(),
        total=0,
        creator_id="c1",
        active_count=0,
        due_this_week_count=0,
        pending_invoices_amount=0.0,
        history=None,
        portfolio_item=None,
        saved_rows=(),
        saved_total=0,
    ):
        self._row = row
        self._rows = list(rows)
        self._total = total
        self._creator_id = creator_id
        self._active_count = active_count
        self._due_this_week_count = due_this_week_count
        self._pending_invoices_amount = pending_invoices_amount
        self._history = history
        self._portfolio_item = portfolio_item
        self._saved_rows = list(saved_rows)
        self._saved_total = saved_total
        self.updated_with = None
        self.inserted_item = None
        self.deleted = None
        self.saved = None
        self.unsaved = None

    async def get_by_id(self, creator_id: str):
        return _make_creator(self._row) if self._row else None

    async def get_by_profile_id(self, profile_id: str):
        return _make_creator(self._row) if self._row else None

    async def list_filtered(self, **kwargs):
        return [_make_creator(r) for r in self._rows], self._total

    async def get_id_by_profile_id(self, profile_id: str):
        return self._creator_id

    async def count_active_collaborations(self, creator_id: str):
        return self._active_count

    async def count_collaborations_due_this_week(self, creator_id: str):
        return self._due_this_week_count

    async def sum_pending_invoice_amount(self, creator_id: str):
        return self._pending_invoices_amount

    async def get_historical_stats(self, creator_id: str, days_ago: int):
        return self._history

    async def update_creator(self, creator_id: str, data: dict):
        self.updated_with = data
        return _make_creator({**self._row, **data}) if self._row else None

    async def get_portfolio_item(self, item_id: str):
        return _make_portfolio_item(self._portfolio_item) if self._portfolio_item else None

    async def insert_portfolio_item(self, data: dict):
        self.inserted_item = data
        return _make_portfolio_item({**data, "id": "pi1", "created_at": "2024-01-01T00:00:00+00:00"})

    async def delete_portfolio_item(self, item_id: str, creator_id: str):
        self.deleted = (item_id, creator_id)
        return []

    async def save_campaign(self, creator_id: str, campaign_id: str):
        self.saved = (creator_id, campaign_id)

    async def unsave_campaign(self, creator_id: str, campaign_id: str):
        self.unsaved = (creator_id, campaign_id)

    async def list_saved_campaigns(self, creator_id: str, page: int = 1, page_size: int = 20):
        return self._saved_rows, self._saved_total


class FakeCampaignRepo:
    def __init__(self, row=None):
        self._row = row

    async def get_by_id(self, campaign_id: str):
        return Campaign.from_row(self._row) if self._row else None


async def test_get_creator_by_id_returns_none_when_missing():
    repo = FakeCreatorRepo(row=None)
    assert await creator_service.get_creator_by_id("missing", repo=repo) is None


async def test_get_creator_by_id_maps_user_id_from_profile_id():
    """Regression: user_id must come from profile_id (the FK IS the profile id),
    not from a joined profiles row that was never selected."""
    repo = FakeCreatorRepo(row=dict(CREATOR_ROW))

    creator = await creator_service.get_creator_by_id("c1", repo=repo)

    assert isinstance(creator, CreatorResponse)
    assert creator.user_id == "p1"
    assert creator.instagram_connected is True


async def test_get_creator_by_id_does_not_leak_instagram_tokens():
    repo = FakeCreatorRepo(row=dict(CREATOR_ROW))

    creator = await creator_service.get_creator_by_id("c1", repo=repo)
    dumped = creator.model_dump()

    assert "instagram_access_token" not in dumped
    assert "instagram_user_id" not in dumped


async def test_list_creators_uses_same_serialization_as_get():
    """One source of truth: list items are CreatorResponse objects identical
    to what the single-item path returns."""
    repo = FakeCreatorRepo(rows=[dict(CREATOR_ROW)], total=1)

    result = await creator_service.list_creators(repo=repo)

    assert result["total"] == 1
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert isinstance(item, CreatorResponse)
    assert item.model_dump() == creator_service._creator_to_response(_make_creator(dict(CREATOR_ROW))).model_dump()


async def test_list_creators_forwards_discovery_filters():
    """Brand discover filters (engagement, verified) must reach the repo."""
    repo = FakeCreatorRepo(rows=[dict(CREATOR_ROW)], total=1)
    captured: dict = {}

    async def capture_list_filtered(**kwargs):
        captured.update(kwargs)
        return [_make_creator(dict(CREATOR_ROW))], 1

    repo.list_filtered = capture_list_filtered  # type: ignore[method-assign]

    await creator_service.list_creators(
        search="delhi",
        niche="Food",
        city=["South Delhi", "Delhi"],
        follower_min=5000,
        follower_max=50000,
        engagement_min=3.0,
        verified_only=True,
        page=2,
        page_size=10,
        repo=repo,
    )

    assert captured["search"] == "delhi"
    assert captured["niche"] == "Food"
    assert captured["city"] == ["South Delhi", "Delhi"]
    assert captured["follower_min"] == 5000
    assert captured["follower_max"] == 50000
    assert captured["engagement_min"] == 3.0
    assert captured["verified_only"] is True
    assert captured["page"] == 2
    assert captured["page_size"] == 10


async def test_get_creator_stats_404_without_creator_profile():
    repo = FakeCreatorRepo(creator_id=None)

    with pytest.raises(HTTPException) as exc_info:
        await creator_service.get_creator_stats(profile_id="p-missing", repo=repo)

    assert exc_info.value.status_code == 404


async def test_get_creator_stats_counts_active_collaborations():
    repo = FakeCreatorRepo(creator_id="c1", active_count=3)

    stats = await creator_service.get_creator_stats(profile_id="p1", repo=repo)

    assert stats.active_collaborations_count == 3


async def test_get_creator_stats_includes_due_this_week_count():
    repo = FakeCreatorRepo(creator_id="c1", due_this_week_count=2)

    stats = await creator_service.get_creator_stats(profile_id="p1", repo=repo)

    assert stats.due_this_week_count == 2


async def test_get_creator_stats_includes_pending_invoices_amount():
    repo = FakeCreatorRepo(creator_id="c1", pending_invoices_amount=12000.0)

    stats = await creator_service.get_creator_stats(profile_id="p1", repo=repo)

    assert stats.pending_invoices_amount == 12000.0


async def test_get_creator_stats_defaults_new_fields_to_zero():
    """A creator with no collaborations/invoices at all should get real
    zeros for the new home-screen stats, not None or a missing field."""
    repo = FakeCreatorRepo(creator_id="c1")

    stats = await creator_service.get_creator_stats(profile_id="p1", repo=repo)

    assert stats.due_this_week_count == 0
    assert stats.pending_invoices_amount == 0.0


# ── Serialization ─────────────────────────────────────


async def test_row_to_creator_response_includes_instagram_handle():
    """Regression: instagram_handle is a public CreatorBase field and must be
    mapped through (it was silently dropped, always serializing as None)."""
    creator = creator_service._creator_to_response(_make_creator(dict(CREATOR_ROW)))

    assert creator.instagram_handle == "@alice"


# ── update_creator ────────────────────────────────────


async def test_update_creator_applies_only_provided_fields():
    repo = FakeCreatorRepo(row=dict(CREATOR_ROW))

    result = await creator_service.update_creator(
        creator_id="c1",
        profile_id="p1",
        role=UserRole.CREATOR,
        data=CreatorUpdateRequest(name="Alice Cooper", tiktok_handle="@alicecooper"),
        repo=repo,
    )

    assert repo.updated_with == {"name": "Alice Cooper", "tiktok_handle": "@alicecooper"}
    assert result.name == "Alice Cooper"
    assert result.city == "Springfield"  # untouched


async def test_update_creator_404_when_creator_missing():
    repo = FakeCreatorRepo(row=None)

    with pytest.raises(HTTPException) as exc_info:
        await creator_service.update_creator(
            creator_id="missing",
            profile_id="p1",
            role=UserRole.CREATOR,
            data=CreatorUpdateRequest(name="X"),
            repo=repo,
        )

    assert exc_info.value.status_code == 404


async def test_update_creator_403_for_non_owner():
    repo = FakeCreatorRepo(row=dict(CREATOR_ROW))  # owned by profile p1

    with pytest.raises(HTTPException) as exc_info:
        await creator_service.update_creator(
            creator_id="c1",
            profile_id="someone-else",
            role=UserRole.CREATOR,
            data=CreatorUpdateRequest(name="X"),
            repo=repo,
        )

    assert exc_info.value.status_code == 403
    assert repo.updated_with is None


async def test_update_creator_allowed_for_superadmin():
    repo = FakeCreatorRepo(row=dict(CREATOR_ROW))

    result = await creator_service.update_creator(
        creator_id="c1",
        profile_id="admin-profile",
        role=UserRole.SUPERADMIN,
        data=CreatorUpdateRequest(bio="edited by admin"),
        repo=repo,
    )

    assert result.bio == "edited by admin"


async def test_update_creator_request_schema_has_no_instagram_fields():
    """Regression: instagram_handle/follower_count must never be
    self-reportable, connected or not — CreatorUpdateRequest doesn't define
    them as fields at all, so passing them is silently a no-op rather than
    something that needs runtime rejection."""
    assert "follower_count" not in CreatorUpdateRequest.model_fields
    assert "instagram_handle" not in CreatorUpdateRequest.model_fields


async def test_update_creator_ignores_follower_count_even_when_not_connected():
    """Extra kwargs Pydantic doesn't recognize are dropped, not stored — so
    even a caller that still sends follower_count in the JSON body can't
    move it, whether or not Instagram is connected."""
    repo = FakeCreatorRepo(row={**CREATOR_ROW, "instagram_access_token": None})

    result = await creator_service.update_creator(
        creator_id="c1",
        profile_id="p1",
        role=UserRole.CREATOR,
        data=CreatorUpdateRequest(**{"name": "Alice Cooper", "follower_count": 1500}),
        repo=repo,
    )

    assert result.name == "Alice Cooper"
    assert result.follower_count == 1000  # untouched — still the original DB value
    assert repo.updated_with == {"name": "Alice Cooper"}


async def test_update_creator_empty_payload_returns_current_without_write():
    repo = FakeCreatorRepo(row=dict(CREATOR_ROW))

    result = await creator_service.update_creator(
        creator_id="c1",
        profile_id="p1",
        role=UserRole.CREATOR,
        data=CreatorUpdateRequest(),
        repo=repo,
    )

    assert repo.updated_with is None  # no DB write happened
    assert result.name == "Alice"


# ── Portfolio add/delete ──────────────────────────────


async def test_add_portfolio_item_happy_path():
    repo = FakeCreatorRepo(row=dict(CREATOR_ROW))

    item = await creator_service.add_portfolio_item(
        creator_id="c1",
        profile_id="p1",
        role=UserRole.CREATOR,
        data=PortfolioItemCreateRequest(
            title="Spring shoot",
            media_url="https://storage.example.com/portfolio/1.jpg",
        ),
        repo=repo,
    )

    assert repo.inserted_item["creator_id"] == "c1"
    assert repo.inserted_item["media_type"] == "photo"  # default
    assert item["id"] == "pi1"
    assert item["title"] == "Spring shoot"


async def test_add_portfolio_item_403_for_non_owner():
    repo = FakeCreatorRepo(row=dict(CREATOR_ROW))

    with pytest.raises(HTTPException) as exc_info:
        await creator_service.add_portfolio_item(
            creator_id="c1",
            profile_id="someone-else",
            role=UserRole.CREATOR,
            data=PortfolioItemCreateRequest(media_url="https://x.com/1.jpg"),
            repo=repo,
        )

    assert exc_info.value.status_code == 403
    assert repo.inserted_item is None


async def test_portfolio_item_create_requires_media_url():
    with pytest.raises(ValidationError):
        PortfolioItemCreateRequest(title="no url")


async def test_delete_portfolio_item_happy_path():
    repo = FakeCreatorRepo(row=dict(CREATOR_ROW), portfolio_item=dict(PORTFOLIO_ITEM_ROW))

    await creator_service.delete_portfolio_item(
        creator_id="c1",
        item_id="pi1",
        profile_id="p1",
        role=UserRole.CREATOR,
        repo=repo,
    )

    assert repo.deleted == ("pi1", "c1")


async def test_delete_portfolio_item_404_when_missing():
    repo = FakeCreatorRepo(row=dict(CREATOR_ROW), portfolio_item=None)

    with pytest.raises(HTTPException) as exc_info:
        await creator_service.delete_portfolio_item(
            creator_id="c1",
            item_id="missing",
            profile_id="p1",
            role=UserRole.CREATOR,
            repo=repo,
        )

    assert exc_info.value.status_code == 404
    assert repo.deleted is None


async def test_delete_portfolio_item_404_when_belongs_to_other_creator():
    """An item_id that exists but under a different creator must 404, not
    delete — otherwise a creator could delete anyone's items by guessing IDs."""
    repo = FakeCreatorRepo(
        row=dict(CREATOR_ROW),
        portfolio_item={**PORTFOLIO_ITEM_ROW, "creator_id": "someone-else"},
    )

    with pytest.raises(HTTPException) as exc_info:
        await creator_service.delete_portfolio_item(
            creator_id="c1",
            item_id="pi1",
            profile_id="p1",
            role=UserRole.CREATOR,
            repo=repo,
        )

    assert exc_info.value.status_code == 404
    assert repo.deleted is None


# ── Saved campaigns ───────────────────────────────────


async def test_save_campaign_upserts_bookmark():
    repo = FakeCreatorRepo(creator_id="c1")
    campaign_repo = FakeCampaignRepo(row=dict(CAMPAIGN_ROW))

    await creator_service.save_campaign(
        profile_id="p1",
        campaign_id="camp1",
        repo=repo,
        campaign_repo=campaign_repo,
    )

    assert repo.saved == ("c1", "camp1")


async def test_save_campaign_404_for_unknown_campaign():
    repo = FakeCreatorRepo(creator_id="c1")
    campaign_repo = FakeCampaignRepo(row=None)

    with pytest.raises(HTTPException) as exc_info:
        await creator_service.save_campaign(
            profile_id="p1",
            campaign_id="missing",
            repo=repo,
            campaign_repo=campaign_repo,
        )

    assert exc_info.value.status_code == 404
    assert repo.saved is None


async def test_save_campaign_404_without_creator_profile():
    repo = FakeCreatorRepo(creator_id=None)
    campaign_repo = FakeCampaignRepo(row=dict(CAMPAIGN_ROW))

    with pytest.raises(HTTPException) as exc_info:
        await creator_service.save_campaign(
            profile_id="p-missing",
            campaign_id="camp1",
            repo=repo,
            campaign_repo=campaign_repo,
        )

    assert exc_info.value.status_code == 404


async def test_unsave_campaign_deletes_bookmark():
    repo = FakeCreatorRepo(creator_id="c1")

    await creator_service.unsave_campaign(profile_id="p1", campaign_id="camp1", repo=repo)

    assert repo.unsaved == ("c1", "camp1")


async def test_list_saved_campaigns_returns_full_campaign_objects():
    """Contract is PaginatedResponse[CampaignResponse] — items must carry the
    full campaign shape (deliverables, description, max_creators, ...), not a
    hand-picked subset that would fail response validation."""
    saved_row = {"creator_id": "c1", "campaign_id": "camp1", "campaigns": dict(CAMPAIGN_ROW)}
    repo = FakeCreatorRepo(creator_id="c1", saved_rows=[saved_row], saved_total=1)

    result = await creator_service.list_saved_campaigns(profile_id="p1", repo=repo)

    assert result["total"] == 1
    item = result["items"][0]
    assert item.id == "camp1"
    assert item.description == "Promote the summer menu"
    assert item.deliverables[0].platform.value == "instagram"
    assert item.max_creators == 5


# ── Payout details ─────────────────────────────────────
#
# Bank/UPI details here are self-reported — there is no penny-drop/IFSC
# lookup or any other real check behind them. `payout_verified` must never
# be set true by this code path; doing so would put a false "Verified"
# badge in front of both the creator and any brand who sees it.


async def test_save_payout_details_bank_does_not_set_verified():
    repo = FakeCreatorRepo(row=dict(CREATOR_ROW))

    result = await creator_service.save_payout_details(
        profile_id="p1",
        data=PayoutSetupRequest(
            method="bank",
            account_name="Alice Cooper",
            account_number="1234567890",
            ifsc_code="hdfc0001234",
            bank_name="HDFC Bank",
        ),
        repo=repo,
    )

    assert "payout_verified" not in repo.updated_with
    assert result["payout_verified"] is False
    assert repo.updated_with["account_number_last4"] == "7890"
    assert repo.updated_with["ifsc_code"] == "HDFC0001234"


async def test_save_payout_details_upi_does_not_set_verified():
    repo = FakeCreatorRepo(row=dict(CREATOR_ROW))

    result = await creator_service.save_payout_details(
        profile_id="p1",
        data=PayoutSetupRequest(method="upi", upi_id="alice@upi"),
        repo=repo,
    )

    assert "payout_verified" not in repo.updated_with
    assert result["payout_verified"] is False


async def test_save_payout_details_never_flips_verified_true_even_when_resaved():
    """Regression guard: even a creator who already has a (legacy/stale)
    payout_verified=True row must not have that echoed back as a fresh
    'verification' — this endpoint has no verification logic at all."""
    repo = FakeCreatorRepo(row={**CREATOR_ROW, "payout_verified": True})

    await creator_service.save_payout_details(
        profile_id="p1",
        data=PayoutSetupRequest(method="upi", upi_id="alice@upi"),
        repo=repo,
    )

    assert "payout_verified" not in repo.updated_with


async def test_save_payout_details_bank_requires_account_and_ifsc():
    repo = FakeCreatorRepo(row=dict(CREATOR_ROW))

    with pytest.raises(HTTPException) as exc_info:
        await creator_service.save_payout_details(
            profile_id="p1",
            data=PayoutSetupRequest(method="bank"),
            repo=repo,
        )

    assert exc_info.value.status_code == 422
    assert repo.updated_with is None


async def test_get_payout_details_reflects_stored_verified_state():
    repo = FakeCreatorRepo(row={**CREATOR_ROW, "payout_verified": False})

    result = await creator_service.get_payout_details(profile_id="p1", repo=repo)

    assert result["payout_verified"] is False
