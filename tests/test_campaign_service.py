"""
Unit tests for campaign_service — repositories injected as fakes, no Supabase.
"""

from datetime import UTC
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.enums import CampaignObjective, CampaignStatus, CompensationType, ContentType, Platform, UserRole
from app.models.campaign import Campaign
from app.models.creator import Creator
from app.schemas.campaign import (
    CampaignCreateRequest,
    CampaignDeliverablesRequest,
    CampaignUpdateRequest,
    DeliverableItem,
)
from app.schemas.user import UserInToken
from app.services import campaign_service

CAMPAIGN_ROW = {
    "id": "camp1",
    "business_id": "b1",
    "title": "Summer Campaign",
    "objective": "brand_awareness",
    "description": "Promote the summer menu",
    "cover_image_url": None,
    "deliverables": [
        {
            "platform": "instagram",
            "content_type": "reel",
            "quantity": 1,
            "description": None,
            "required": True,
        }
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
    "deadline": "2024-12-31T00:00:00+00:00",
    "status": "active",
    "created_at": "2024-01-01T00:00:00+00:00",
}


class FakeCampaignRepo:
    def __init__(self, row=None, list_rows=None, total=None, counts=None, budget_bounds=None):
        self._row = row if row is not None else dict(CAMPAIGN_ROW)
        self._list_rows = list_rows
        self._total = total
        self._counts = counts or {}
        self._budget_bounds = budget_bounds if budget_bounds is not None else {"min": None, "max": None}
        self.updated = None
        self.inserted = None
        self.deleted = None
        self.list_kwargs = None

    async def get_budget_bounds(self):
        return self._budget_bounds

    async def get_by_id(self, campaign_id: str):
        return Campaign.from_row(self._row) if self._row else None

    async def fetch_application_counts(self, campaign_ids: list[str]):
        return {
            cid: {
                "applicant_count": self._counts.get("applicant_count", 0),
                "accepted_count": self._counts.get("accepted_count", 0),
                "posted_count": self._counts.get("posted_count", 0),
            }
            for cid in campaign_ids
        }

    async def fetch_posted_counts(self, campaign_ids: list[str]):
        return {cid: self._counts.get("posted_count", 0) for cid in campaign_ids}

    async def update_campaign(self, campaign_id: str, data: dict):
        self.updated = data
        row = {**self._row, **data}
        self._row = row
        return Campaign.from_row(row)

    async def insert_campaign(self, data: dict):
        self.inserted = data
        row = {
            **CAMPAIGN_ROW,
            **data,
            "id": "camp-new",
            "created_at": "2024-01-01T00:00:00+00:00",
            "deliverables": data.get("deliverables", []),
            "compensation_type": data.get("compensation_type"),
            "deadline": data.get("deadline"),
        }
        return Campaign.from_row(row)

    async def delete_campaign(self, campaign_id: str):
        self.deleted = campaign_id

    async def list_active(
        self, search=None, category=None, page=1, page_size=20, *, extra_category_values=None, **kwargs
    ):
        self.list_kwargs = {
            "search": search,
            "category": category,
            "page": page,
            "page_size": page_size,
            "extra_category_values": extra_category_values,
            **kwargs,
        }
        rows = self._list_rows if self._list_rows is not None else [self._row]
        return [Campaign.from_row(r) for r in rows], self._total if self._total is not None else len(rows)


class FakeBusinessRepo:
    """`owner_profile_id` defaults to the "p-business" convention used
    throughout this file's write-path tests — it backs the owner-equality
    fast path in business_access.get_role_for_profile (see
    app/services/business_access.py), which every mutating campaign_service
    call now goes through for team-account role gating."""

    def __init__(self, business_id: str | None = "b1", businesses=None, owner_profile_id: str = "p-business"):
        self._business_id = business_id
        self._businesses = businesses or []
        self._owner_profile_id = owner_profile_id

    async def get_id_by_profile_id(self, profile_id: str):
        return self._business_id

    async def get_by_ids(self, business_ids: list[str]):
        return [b for b in self._businesses if b.id in business_ids]

    async def get_by_id(self, business_id: str):
        if business_id != self._business_id:
            return None
        return SimpleNamespace(id=business_id, profile_id=self._owner_profile_id)


class FakeCreatorRepo:
    def __init__(self, niche: str | None = None, creator=None):
        self._niche = niche
        self._creator = creator

    async def get_niche_by_profile_id(self, profile_id: str):
        return self._niche

    async def get_by_id(self, creator_id: str):
        return self._creator

    async def get_by_profile_id(self, profile_id: str):
        return self._creator


class FakeApplicationRepo:
    def __init__(self, existing=None, applications=None, total=0):
        self._existing = existing
        self._applications = applications or []
        self._total = total
        self.inserted = None
        self.list_kwargs = None

    async def get_existing(self, campaign_id, creator_id):
        from app.models.application import CampaignApplication
        return CampaignApplication.from_row(self._existing) if self._existing else None

    async def insert_application(self, data: dict):
        from app.models.application import CampaignApplication
        self.inserted = data
        row = {**data, "id": "app-new", "created_at": "2024-01-01T00:00:00+00:00"}
        return CampaignApplication.from_row(row)

    async def list_by_campaign(self, campaign_id, page=1, page_size=20):
        self.list_kwargs = {"campaign_id": campaign_id, "page": page, "page_size": page_size}
        return self._applications, self._total


class FakeCollaborationRepo:
    def __init__(self, collaborations=None, submissions_by_collab=None):
        self._collaborations = collaborations or []
        self._submissions_by_collab = submissions_by_collab or {}

    async def list_by_campaign(self, campaign_id, page=1, page_size=20):
        return self._collaborations, len(self._collaborations)

    async def list_submissions(self, collaboration_id):
        return self._submissions_by_collab.get(collaboration_id, [])


class FakeInvoiceRepo:
    def __init__(self, invoices=None):
        self._invoices = invoices or []

    async def list_by_collaboration_ids(self, collaboration_ids):
        return [i for i in self._invoices if i.collaboration_id in collaboration_ids]


def _business_user(profile_id: str = "p-business") -> UserInToken:
    return UserInToken(
        id=profile_id,
        auth_id="auth-business",
        email="biz@example.com",
        role=UserRole.BUSINESS,
        is_active=True,
    )


def _creator_user(profile_id: str = "p-creator") -> UserInToken:
    return UserInToken(
        id=profile_id,
        auth_id="auth-creator",
        email="creator@example.com",
        role=UserRole.CREATOR,
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


@pytest.fixture(autouse=True)
def _stub_notifications(monkeypatch):
    sent = []

    async def _fake_create_notification(profile_id, type, title, body, related_id=None, **kwargs):
        sent.append(
            {
                "profile_id": profile_id,
                "type": type,
                "title": title,
                "body": body,
                "related_id": related_id,
            }
        )

    monkeypatch.setattr(
        campaign_service.notification_service, "create_notification", _fake_create_notification
    )
    return sent


# ── get_campaign / draft access ───────────────────────


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


# ── publish validation ────────────────────────────────


async def test_publish_campaign_succeeds_when_complete():
    repo = FakeCampaignRepo(row={**CAMPAIGN_ROW, "status": "draft"})
    business_repo = FakeBusinessRepo(business_id="b1")

    result = await campaign_service.publish_campaign(
        "camp1", "p-business", campaign_repo=repo, business_repo=business_repo
    )

    assert result.status == CampaignStatus.ACTIVE
    assert repo.updated["status"] == "active"


async def test_publish_campaign_rejects_missing_fields():
    incomplete = {
        **CAMPAIGN_ROW,
        "status": "draft",
        "deliverables": [],
        "creator_category": "",
        "location": "",
        "deadline": None,
    }
    repo = FakeCampaignRepo(row=incomplete)
    business_repo = FakeBusinessRepo(business_id="b1")

    with pytest.raises(HTTPException) as exc:
        await campaign_service.publish_campaign(
            "camp1", "p-business", campaign_repo=repo, business_repo=business_repo
        )

    assert exc.value.status_code == 422
    assert "missing_fields" in exc.value.detail


async def test_publish_campaign_rejects_non_owner():
    repo = FakeCampaignRepo(row={**CAMPAIGN_ROW, "status": "draft"})
    business_repo = FakeBusinessRepo(business_id="other-biz")

    with pytest.raises(HTTPException) as exc:
        await campaign_service.publish_campaign(
            "camp1", "p-business", campaign_repo=repo, business_repo=business_repo
        )

    assert exc.value.status_code == 403


# ── deliverables enum serialization ───────────────────


async def test_update_campaign_deliverables_serializes_enums_as_strings():
    repo = FakeCampaignRepo(row={**CAMPAIGN_ROW, "status": "draft"})
    business_repo = FakeBusinessRepo(business_id="b1")
    data = CampaignDeliverablesRequest(
        deliverables=[
            DeliverableItem(
                platform=Platform.INSTAGRAM,
                content_type=ContentType.REEL,
                quantity=2,
                description="Reel about menu",
            )
        ],
        compensation_type=CompensationType.CASH,
        cash_amount_min=50,
        cash_amount_max=100,
    )

    await campaign_service.update_campaign_deliverables(
        "camp1", "p-business", data, campaign_repo=repo, business_repo=business_repo
    )

    deliverable = repo.updated["deliverables"][0]
    assert deliverable["platform"] == "instagram"
    assert deliverable["content_type"] == "reel"
    assert isinstance(deliverable["platform"], str)
    assert isinstance(deliverable["content_type"], str)


async def test_update_campaign_deliverables_product_clears_cash_amounts():
    repo = FakeCampaignRepo(
        row={
            **CAMPAIGN_ROW,
            "status": "draft",
            "compensation_type": "cash",
            "cash_amount_min": 1000.0,
            "cash_amount_max": 2000.0,
        }
    )
    business_repo = FakeBusinessRepo(business_id="b1")
    data = CampaignDeliverablesRequest(
        deliverables=[
            DeliverableItem(
                platform=Platform.INSTAGRAM,
                content_type=ContentType.REEL,
                quantity=1,
            )
        ],
        compensation_type=CompensationType.PRODUCT,
        free_product_description="Free merch kit",
    )

    await campaign_service.update_campaign_deliverables(
        "camp1", "p-business", data, campaign_repo=repo, business_repo=business_repo
    )

    assert repo.updated["compensation_type"] == "product"
    assert repo.updated["cash_amount_min"] is None
    assert repo.updated["cash_amount_max"] is None
    assert repo.updated["free_product_description"] == "Free merch kit"


async def test_update_campaign_general_serializes_deadline_as_iso_string():
    """Regression: bare datetime in update payload caused opaque 500 on PATCH."""
    from datetime import datetime

    repo = FakeCampaignRepo(row={**CAMPAIGN_ROW, "status": "draft", "deadline": None})
    business_repo = FakeBusinessRepo(business_id="b1")
    deadline = datetime(2026, 9, 15, 23, 59, 59, tzinfo=UTC)
    data = CampaignUpdateRequest(deadline=deadline)

    await campaign_service.update_campaign_general(
        "camp1", "p-business", data, campaign_repo=repo, business_repo=business_repo
    )

    assert isinstance(repo.updated["deadline"], str)
    assert "2026-09-15" in repo.updated["deadline"]


# ── recommended niche mapping ─────────────────────────


async def test_list_campaigns_recommended_maps_niche_label_to_category():
    repo = FakeCampaignRepo()
    creator_repo = FakeCreatorRepo(niche="Food & Dining")
    business_repo = FakeBusinessRepo()

    await campaign_service.list_campaigns(
        search=None,
        category=None,
        recommended=True,
        page=1,
        page_size=20,
        user=_creator_user(),
        campaign_repo=repo,
        creator_repo=creator_repo,
        business_repo=business_repo,
    )

    assert repo.list_kwargs["category"] == "food"


async def test_list_campaigns_recommended_maps_niche_value():
    repo = FakeCampaignRepo()
    creator_repo = FakeCreatorRepo(niche="fashion")
    business_repo = FakeBusinessRepo()

    await campaign_service.list_campaigns(
        search=None,
        category=None,
        recommended=True,
        page=1,
        page_size=20,
        user=_creator_user(),
        campaign_repo=repo,
        creator_repo=creator_repo,
        business_repo=business_repo,
    )

    assert repo.list_kwargs["category"] == "fashion"


async def test_list_campaigns_recommended_ignores_unmapped_niche():
    repo = FakeCampaignRepo()
    creator_repo = FakeCreatorRepo(niche="obscure niche xyz")
    business_repo = FakeBusinessRepo()

    await campaign_service.list_campaigns(
        search=None,
        category=None,
        recommended=True,
        page=1,
        page_size=20,
        user=_creator_user(),
        campaign_repo=repo,
        creator_repo=creator_repo,
        business_repo=business_repo,
    )

    assert repo.list_kwargs["category"] is None


async def test_list_campaigns_search_maps_category_labels():
    repo = FakeCampaignRepo()
    business_repo = FakeBusinessRepo()

    await campaign_service.list_campaigns(
        search="Food & Dining",
        category=None,
        recommended=None,
        page=1,
        page_size=20,
        user=_creator_user(),
        campaign_repo=repo,
        business_repo=business_repo,
    )

    assert "food" in (repo.list_kwargs["extra_category_values"] or [])


# ── only_qualified ────────────────────────────────────


async def test_list_campaigns_only_qualified_passes_creator_numbers():
    """The repo can't reach the creator's profile — the service has to hand it
    the follower count and engagement rate to filter on."""
    repo = FakeCampaignRepo()
    creator = Creator.from_row(
        {
            "id": "c1",
            "profile_id": "p-creator",
            "name": "Alice",
            "follower_count": 24000,
            "engagement_rate": 6.2,
            "created_at": "2024-01-01T00:00:00+00:00",
        }
    )

    await campaign_service.list_campaigns(
        search=None,
        category=None,
        recommended=None,
        page=1,
        page_size=20,
        only_qualified=True,
        user=_creator_user(),
        campaign_repo=repo,
        creator_repo=FakeCreatorRepo(creator=creator),
        business_repo=FakeBusinessRepo(),
    )

    assert repo.list_kwargs["only_qualified"] is True
    assert repo.list_kwargs["creator_follower_count"] == 24000
    assert repo.list_kwargs["creator_engagement_rate"] == 6.2


async def test_list_campaigns_only_qualified_without_creator_profile():
    """No creator row (or no synced numbers) → no bogus filters get applied."""
    repo = FakeCampaignRepo()

    await campaign_service.list_campaigns(
        search=None,
        category=None,
        recommended=None,
        page=1,
        page_size=20,
        only_qualified=True,
        user=_creator_user(),
        campaign_repo=repo,
        creator_repo=FakeCreatorRepo(creator=None),
        business_repo=FakeBusinessRepo(),
    )

    assert repo.list_kwargs["creator_follower_count"] is None
    assert repo.list_kwargs["creator_engagement_rate"] is None


async def test_list_campaigns_skips_creator_lookup_without_only_qualified():
    repo = FakeCampaignRepo()

    await campaign_service.list_campaigns(
        search=None,
        category=None,
        recommended=None,
        page=1,
        page_size=20,
        user=_creator_user(),
        campaign_repo=repo,
        creator_repo=FakeCreatorRepo(creator=None),
        business_repo=FakeBusinessRepo(),
    )

    assert repo.list_kwargs["creator_follower_count"] is None


# ── budget_min / budget_max (filter-sheet slider) ─────


async def test_list_campaigns_passes_budget_bounds_to_repo():
    repo = FakeCampaignRepo()
    business_repo = FakeBusinessRepo()
    await campaign_service.list_campaigns(
        search=None,
        category=None,
        recommended=None,
        page=1,
        page_size=20,
        budget_min=10000,
        budget_max=25000,
        user=_creator_user(),
        campaign_repo=repo,
        business_repo=business_repo,
    )
    assert repo.list_kwargs["budget_min"] == 10000
    assert repo.list_kwargs["budget_max"] == 25000


async def test_list_campaigns_defaults_budget_bounds_to_none():
    """Slider left at its full span → filter is skipped, not clamped to 0."""
    repo = FakeCampaignRepo()
    business_repo = FakeBusinessRepo()
    await campaign_service.list_campaigns(
        search=None,
        category=None,
        recommended=None,
        page=1,
        page_size=20,
        user=_creator_user(),
        campaign_repo=repo,
        business_repo=business_repo,
    )
    assert repo.list_kwargs["budget_min"] is None
    assert repo.list_kwargs["budget_max"] is None


async def test_get_budget_bounds_returns_real_repo_values():
    repo = FakeCampaignRepo(budget_bounds={"min": 5000.0, "max": 75000.0})
    result = await campaign_service.get_budget_bounds(campaign_repo=repo)
    assert result.min_budget == 5000.0
    assert result.max_budget == 75000.0


async def test_get_budget_bounds_falls_back_when_no_cash_campaigns():
    """No cash campaigns yet (or a brand-new environment) → sane default span,
    not a crash or a degenerate 0–0 slider."""
    repo = FakeCampaignRepo(budget_bounds={"min": None, "max": None})
    result = await campaign_service.get_budget_bounds(campaign_repo=repo)
    assert result.min_budget == 0.0
    assert result.max_budget == 100_000.0


# ── invite_creator active guard ───────────────────────


async def test_invite_creator_rejects_non_active_campaign():
    repo = FakeCampaignRepo(row={**CAMPAIGN_ROW, "status": "draft"})
    business_repo = FakeBusinessRepo(business_id="b1")
    creator = Creator.from_row(
        {
            "id": "c1",
            "profile_id": "p-creator",
            "name": "Alice",
            "created_at": "2024-01-01T00:00:00+00:00",
        }
    )

    with pytest.raises(HTTPException) as exc:
        await campaign_service.invite_creator(
            campaign_id="camp1",
            profile_id="p-business",
            creator_id="c1",
            message="Join us!",
            campaign_repo=repo,
            business_repo=business_repo,
            creator_repo=FakeCreatorRepo(creator=creator),
            app_repo=FakeApplicationRepo(),
        )

    assert exc.value.status_code == 400
    assert "not open for invites" in exc.value.detail


async def test_invite_creator_succeeds_on_active_campaign(_stub_notifications):
    repo = FakeCampaignRepo(row=dict(CAMPAIGN_ROW))
    business_repo = FakeBusinessRepo(business_id="b1")
    creator = Creator.from_row(
        {
            "id": "c1",
            "profile_id": "p-creator",
            "name": "Alice",
            "created_at": "2024-01-01T00:00:00+00:00",
        }
    )
    app_repo = FakeApplicationRepo()

    result = await campaign_service.invite_creator(
        campaign_id="camp1",
        profile_id="p-business",
        creator_id="c1",
        message="Join us!",
        campaign_repo=repo,
        business_repo=business_repo,
        creator_repo=FakeCreatorRepo(creator=creator),
        app_repo=app_repo,
    )

    assert result.status.value == "pending"
    assert app_repo.inserted["direction"] == "business_invited"
    assert len(_stub_notifications) == 1


# ── close / complete lifecycle ────────────────────────


async def test_close_campaign_from_active():
    repo = FakeCampaignRepo(row=dict(CAMPAIGN_ROW))
    business_repo = FakeBusinessRepo(business_id="b1")

    result = await campaign_service.close_campaign(
        "camp1", "p-business", campaign_repo=repo, business_repo=business_repo
    )

    assert result.status == CampaignStatus.CLOSED
    assert repo.updated["status"] == "closed"


async def test_close_campaign_rejects_draft():
    repo = FakeCampaignRepo(row={**CAMPAIGN_ROW, "status": "draft"})
    business_repo = FakeBusinessRepo(business_id="b1")

    with pytest.raises(HTTPException) as exc:
        await campaign_service.close_campaign(
            "camp1", "p-business", campaign_repo=repo, business_repo=business_repo
        )

    assert exc.value.status_code == 400


async def test_complete_campaign_from_closed():
    repo = FakeCampaignRepo(row={**CAMPAIGN_ROW, "status": "closed"})
    business_repo = FakeBusinessRepo(business_id="b1")

    result = await campaign_service.complete_campaign(
        "camp1", "p-business", campaign_repo=repo, business_repo=business_repo
    )

    assert result.status == CampaignStatus.COMPLETED


async def test_complete_campaign_rejects_draft():
    repo = FakeCampaignRepo(row={**CAMPAIGN_ROW, "status": "draft"})
    business_repo = FakeBusinessRepo(business_id="b1")

    with pytest.raises(HTTPException) as exc:
        await campaign_service.complete_campaign(
            "camp1", "p-business", campaign_repo=repo, business_repo=business_repo
        )

    assert exc.value.status_code == 400


# ── applications pagination ───────────────────────────


async def test_list_campaign_applications_returns_paginated_shape():
    from app.models.application import CampaignApplication

    app = CampaignApplication.from_row(
        {
            "id": "app1",
            "campaign_id": "camp1",
            "creator_id": "c1",
            "direction": "creator_applied",
            "status": "pending",
            "created_at": "2024-01-01T00:00:00+00:00",
            "creators": {
                "id": "c1",
                "name": "Alice",
                "profile_photo_url": None,
                "follower_count": 1000,
                "niche": "food",
            },
        }
    )
    app_repo = FakeApplicationRepo(applications=[app], total=1)
    repo = FakeCampaignRepo()
    business_repo = FakeBusinessRepo(business_id="b1")

    result = await campaign_service.list_campaign_applications(
        "camp1",
        "p-business",
        page=1,
        page_size=10,
        campaign_repo=repo,
        business_repo=business_repo,
        app_repo=app_repo,
    )

    assert "items" in result
    assert result["total"] == 1
    assert result["page"] == 1
    assert result["page_size"] == 10
    assert len(result["items"]) == 1
    assert app_repo.list_kwargs == {"campaign_id": "camp1", "page": 1, "page_size": 10}


async def test_list_campaign_applications_rejects_non_owner():
    repo = FakeCampaignRepo()
    business_repo = FakeBusinessRepo(business_id="other-biz")

    with pytest.raises(HTTPException) as exc:
        await campaign_service.list_campaign_applications(
            "camp1",
            "p-business",
            campaign_repo=repo,
            business_repo=business_repo,
            app_repo=FakeApplicationRepo(),
        )

    assert exc.value.status_code == 403


# ── niche helper ──────────────────────────────────────


def test_niche_to_category_maps_labels_and_values():
    assert campaign_service._niche_to_category("Food & Dining") == "food"
    assert campaign_service._niche_to_category("tech") == "tech"
    assert campaign_service._niche_to_category("unknown niche") is None


async def test_create_campaign_step1_creates_draft():
    repo = FakeCampaignRepo()
    business_repo = FakeBusinessRepo(business_id="b1")

    result = await campaign_service.create_campaign_step1(
        "p-business",
        CampaignCreateRequest(
            title="New Campaign",
            objective=CampaignObjective.BRAND_AWARENESS,
            description="Desc",
        ),
        campaign_repo=repo,
        business_repo=business_repo,
    )

    assert result.status == CampaignStatus.DRAFT
    assert repo.inserted["status"] == "draft"
    assert repo.inserted["business_id"] == "b1"


async def test_update_campaign_general_persists_brief_fields():
    repo = FakeCampaignRepo()
    business_repo = FakeBusinessRepo(business_id="b1")

    result = await campaign_service.update_campaign_general(
        "camp1",
        "p-business",
        CampaignUpdateRequest(
            objective=CampaignObjective.ENGAGEMENT,
            platforms=["instagram", "youtube"],
            product_promoted="New weekend brunch menu",
            audience_age_range="22–35",
            audience_gender="All genders",
            audience_location="South Delhi",
            audience_interests="Brunch, food photography",
            key_messaging="Highlight the new menu",
            dos="Tag @brand, natural light",
            donts="No competitor mentions",
            reference_image_urls=["https://cdn.example/ref.jpg"],
            max_creators=20,
        ),
        campaign_repo=repo,
        business_repo=business_repo,
    )

    assert repo.updated["objective"] == "engagement"
    assert repo.updated["platforms"] == ["instagram", "youtube"]
    assert repo.updated["product_promoted"] == "New weekend brunch menu"
    assert repo.updated["max_creators"] == 20
    assert result.product_promoted == "New weekend brunch menu"
    assert result.platforms == ["instagram", "youtube"]
    assert result.key_messaging == "Highlight the new menu"


async def test_get_campaign_includes_posted_count():
    repo = FakeCampaignRepo(counts={"applicant_count": 14, "accepted_count": 8, "posted_count": 3})

    result = await campaign_service.get_campaign("camp1", user=None, campaign_repo=repo)

    assert result.applicant_count == 14
    assert result.accepted_count == 8
    assert result.posted_count == 3


# ── campaign analytics ──────────────────────────────────
from app.core.enums import ApplicationStatus, InvoiceStatus  # noqa: E402
from app.models.application import CampaignApplication  # noqa: E402
from app.models.collaboration import Collaboration  # noqa: E402
from app.models.invoice import Invoice  # noqa: E402


def _application(status: ApplicationStatus) -> CampaignApplication:
    return CampaignApplication(id=f"app-{status.value}", campaign_id="camp1", creator_id="c1", status=status)


def _collaboration(collab_id: str, creator_id: str) -> Collaboration:
    return Collaboration(id=collab_id, campaign_id="camp1", creator_id=creator_id, business_id="b1")


def _invoice(collaboration_id: str, amount: float, status: InvoiceStatus) -> Invoice:
    return Invoice(
        id=f"inv-{collaboration_id}",
        collaboration_id=collaboration_id,
        creator_id="c1",
        business_id="b1",
        total_amount=amount,
        status=status,
    )


async def test_campaign_analytics_rejects_non_owner():
    repo = FakeCampaignRepo(row=dict(CAMPAIGN_ROW))
    business_repo = FakeBusinessRepo(business_id="someone-else")

    with pytest.raises(HTTPException) as exc:
        await campaign_service.get_campaign_analytics(
            "camp1",
            "p-business",
            campaign_repo=repo,
            business_repo=business_repo,
            application_repo=FakeApplicationRepo(),
            collaboration_repo=FakeCollaborationRepo(),
            invoice_repo=FakeInvoiceRepo(),
        )

    assert exc.value.status_code == 403


async def test_campaign_analytics_computes_rates_and_spend():
    repo = FakeCampaignRepo(row=dict(CAMPAIGN_ROW))
    business_repo = FakeBusinessRepo(business_id="b1")
    applications = [
        _application(ApplicationStatus.ACCEPTED),
        _application(ApplicationStatus.ACCEPTED),
        _application(ApplicationStatus.REJECTED),
        _application(ApplicationStatus.PENDING),
    ]
    collaborations = [
        _collaboration("collab1", "c1"),
        _collaboration("collab2", "c2"),
    ]
    invoices = [
        _invoice("collab1", 10000.0, InvoiceStatus.PAID),
        _invoice("collab2", 5000.0, InvoiceStatus.SENT),
    ]

    result = await campaign_service.get_campaign_analytics(
        "camp1",
        "p-business",
        campaign_repo=repo,
        business_repo=business_repo,
        application_repo=FakeApplicationRepo(applications=applications, total=len(applications)),
        collaboration_repo=FakeCollaborationRepo(collaborations=collaborations),
        invoice_repo=FakeInvoiceRepo(invoices=invoices),
    )

    assert result.applied_count == 4
    assert result.accepted_count == 2
    assert result.rejected_count == 1
    assert result.response_rate == 75.0  # 3 decided / 4 applied
    assert result.acceptance_rate == pytest.approx(66.7, rel=1e-2)  # 2 accepted / 3 decided
    assert result.creators_engaged == 2
    assert result.invoiced_amount == 15000.0
    assert result.paid_amount == 10000.0
    assert result.cost_per_creator == 7500.0
    assert result.content_metrics_available is False


async def test_campaign_analytics_content_metrics_available_when_submissions_exist():
    repo = FakeCampaignRepo(row=dict(CAMPAIGN_ROW))
    business_repo = FakeBusinessRepo(business_id="b1")
    collaborations = [_collaboration("collab1", "c1")]

    result = await campaign_service.get_campaign_analytics(
        "camp1",
        "p-business",
        campaign_repo=repo,
        business_repo=business_repo,
        application_repo=FakeApplicationRepo(),
        collaboration_repo=FakeCollaborationRepo(
            collaborations=collaborations,
            submissions_by_collab={"collab1": [{"id": "sub1"}]},
        ),
        invoice_repo=FakeInvoiceRepo(),
    )

    assert result.content_metrics_available is True


async def test_campaign_analytics_handles_zero_applications_and_creators():
    repo = FakeCampaignRepo(row=dict(CAMPAIGN_ROW))
    business_repo = FakeBusinessRepo(business_id="b1")

    result = await campaign_service.get_campaign_analytics(
        "camp1",
        "p-business",
        campaign_repo=repo,
        business_repo=business_repo,
        application_repo=FakeApplicationRepo(),
        collaboration_repo=FakeCollaborationRepo(),
        invoice_repo=FakeInvoiceRepo(),
    )

    assert result.applied_count == 0
    assert result.response_rate is None
    assert result.acceptance_rate is None
    assert result.cost_per_creator is None
