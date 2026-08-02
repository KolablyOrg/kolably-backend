"""
Unit tests for campaign_service — repositories injected as fakes, no Supabase.
"""

import pytest
from fastapi import HTTPException

from app.core.enums import CampaignStatus, CompensationType, ContentType, Platform, UserRole
from app.models.campaign import Campaign
from app.models.creator import Creator
from app.schemas.campaign import (
    CampaignCreateRequest,
    CampaignDeliverablesRequest,
    DeliverableItem,
)
from app.schemas.user import UserInToken
from app.services import campaign_service
from app.core.enums import CampaignObjective

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
    def __init__(self, row=None, list_rows=None, total=None):
        self._row = row if row is not None else dict(CAMPAIGN_ROW)
        self._list_rows = list_rows
        self._total = total
        self.updated = None
        self.inserted = None
        self.deleted = None
        self.list_kwargs = None

    async def get_by_id(self, campaign_id: str):
        return Campaign.from_row(self._row) if self._row else None

    async def fetch_application_counts(self, campaign_ids: list[str]):
        return {}

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

    async def list_active(self, search=None, category=None, page=1, page_size=20, *, extra_category_values=None):
        self.list_kwargs = {
            "search": search,
            "category": category,
            "page": page,
            "page_size": page_size,
            "extra_category_values": extra_category_values,
        }
        rows = self._list_rows if self._list_rows is not None else [self._row]
        return [Campaign.from_row(r) for r in rows], self._total if self._total is not None else len(rows)


class FakeBusinessRepo:
    def __init__(self, business_id: str | None = "b1", businesses=None):
        self._business_id = business_id
        self._businesses = businesses or []

    async def get_id_by_profile_id(self, profile_id: str):
        return self._business_id

    async def get_by_ids(self, business_ids: list[str]):
        return [b for b in self._businesses if b.id in business_ids]


class FakeCreatorRepo:
    def __init__(self, niche: str | None = None, creator=None):
        self._niche = niche
        self._creator = creator

    async def get_niche_by_profile_id(self, profile_id: str):
        return self._niche

    async def get_by_id(self, creator_id: str):
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
