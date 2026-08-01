"""
Unit tests for application_service — repositories injected as fakes, no Supabase.
"""

import pytest
from fastapi import HTTPException

from app.models.application import CampaignApplication
from app.models.business import Business
from app.models.campaign import Campaign
from app.models.creator import Creator
from app.schemas.application import ApplicationCreateRequest
from app.services import application_service

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

CREATOR_ROW = {
    "id": "c1",
    "profile_id": "p-creator",
    "name": "Alice",
    "created_at": "2024-01-01T00:00:00+00:00",
}

BUSINESS_ROW = {
    "id": "b1",
    "profile_id": "p-business",
    "business_name": "Acme Co",
    "city": "Springfield",
    "category": "food",
    "created_at": "2024-01-01T00:00:00+00:00",
}

APPLICATION_ROW = {
    "id": "app1",
    "campaign_id": "camp1",
    "creator_id": "c1",
    "direction": "creator_applied",
    "message": "I'd love to work on this!",
    "status": "pending",
    "created_at": "2024-01-01T00:00:00+00:00",
}


class FakeCreatorRepo:
    def __init__(self, creator_id="c1", row=None):
        self._creator_id = creator_id
        self._row = row or dict(CREATOR_ROW)

    async def get_id_by_profile_id(self, profile_id: str):
        return self._creator_id

    async def get_by_id(self, creator_id: str):
        return Creator.from_row(self._row) if self._row else None


class FakeBusinessRepo:
    def __init__(self, business_id="b1", row=None):
        self._business_id = business_id
        self._row = row or dict(BUSINESS_ROW)

    async def get_id_by_profile_id(self, profile_id: str):
        return self._business_id

    async def get_by_id(self, business_id: str):
        return Business.from_row(self._row) if self._row else None


class FakeCampaignRepo:
    def __init__(self, row=None):
        self._row = row if row is not None else dict(CAMPAIGN_ROW)

    async def get_by_id(self, campaign_id: str):
        return Campaign.from_row(self._row) if self._row else None


class FakeApplicationRepo:
    def __init__(self, existing=None, row=None):
        self._existing = existing
        self._row = row
        self.inserted = None
        self.status_updates = []
        self.deleted = None

    async def get_existing(self, campaign_id, creator_id):
        return CampaignApplication.from_row(self._existing) if self._existing else None

    async def insert_application(self, data: dict):
        self.inserted = data
        row = {**data, "id": "app-new", "created_at": "2024-01-01T00:00:00+00:00"}
        return CampaignApplication.from_row(row)

    async def get_by_id(self, application_id: str):
        return CampaignApplication.from_row(self._row) if self._row else None

    async def update_status(self, application_id: str, status: str):
        self.status_updates.append((application_id, status))
        row = {**self._row, "status": status}
        return CampaignApplication.from_row(row)

    async def delete_application(self, application_id: str):
        self.deleted = application_id


class FakeCollaborationRepo:
    def __init__(self):
        self.inserted = None

    async def insert_collaboration(self, data: dict):
        self.inserted = data
        row = {**data, "id": "collab1", "created_at": "2024-01-01T00:00:00+00:00", "completed_at": None}
        from app.models.collaboration import Collaboration
        return Collaboration.from_row(row)


@pytest.fixture(autouse=True)
def _stub_notifications(monkeypatch):
    sent = []

    async def _fake_create_notification(profile_id, type, title, body, related_id=None, **kwargs):
        sent.append({"profile_id": profile_id, "type": type, "title": title, "body": body, "related_id": related_id})

    monkeypatch.setattr(application_service.notification_service, "create_notification", _fake_create_notification)
    return sent


async def test_apply_to_campaign_creates_pending_application_and_notifies_business(_stub_notifications):
    result = await application_service.apply_to_campaign(
        profile_id="p-creator",
        data=ApplicationCreateRequest(campaign_id="camp1", message="Pick me!"),
        creator_repo=FakeCreatorRepo(),
        campaign_repo=FakeCampaignRepo(),
        business_repo=FakeBusinessRepo(),
        app_repo=FakeApplicationRepo(),
    )

    assert result.status.value == "pending"
    assert result.direction.value == "creator_applied"
    assert len(_stub_notifications) == 1
    assert _stub_notifications[0]["profile_id"] == "p-business"
    assert _stub_notifications[0]["type"].value == "application_received"


async def test_apply_to_campaign_rejects_duplicate():
    with pytest.raises(HTTPException) as exc:
        await application_service.apply_to_campaign(
            profile_id="p-creator",
            data=ApplicationCreateRequest(campaign_id="camp1"),
            creator_repo=FakeCreatorRepo(),
            campaign_repo=FakeCampaignRepo(),
            business_repo=FakeBusinessRepo(),
            app_repo=FakeApplicationRepo(existing=dict(APPLICATION_ROW)),
        )
    assert exc.value.status_code == 409


async def test_apply_to_campaign_rejects_non_active_campaign():
    with pytest.raises(HTTPException) as exc:
        await application_service.apply_to_campaign(
            profile_id="p-creator",
            data=ApplicationCreateRequest(campaign_id="camp1"),
            creator_repo=FakeCreatorRepo(),
            campaign_repo=FakeCampaignRepo(row={**CAMPAIGN_ROW, "status": "draft"}),
            business_repo=FakeBusinessRepo(),
            app_repo=FakeApplicationRepo(),
        )
    assert exc.value.status_code == 400


async def test_withdraw_application_deletes_pending_own_application():
    app_repo = FakeApplicationRepo(row=dict(APPLICATION_ROW))

    result = await application_service.withdraw_application(
        application_id="app1",
        profile_id="p-creator",
        creator_repo=FakeCreatorRepo(),
        app_repo=app_repo,
    )

    assert result["message"] == "Application withdrawn"
    assert app_repo.deleted == "app1"


async def test_withdraw_application_rejects_other_creators_application():
    app_repo = FakeApplicationRepo(row=dict(APPLICATION_ROW))

    with pytest.raises(HTTPException) as exc:
        await application_service.withdraw_application(
            application_id="app1",
            profile_id="p-other",
            creator_repo=FakeCreatorRepo(creator_id="c-other"),
            app_repo=app_repo,
        )
    assert exc.value.status_code == 403


async def test_withdraw_application_rejects_already_decided():
    app_repo = FakeApplicationRepo(row={**APPLICATION_ROW, "status": "accepted"})

    with pytest.raises(HTTPException) as exc:
        await application_service.withdraw_application(
            application_id="app1",
            profile_id="p-creator",
            creator_repo=FakeCreatorRepo(),
            app_repo=app_repo,
        )
    assert exc.value.status_code == 400


async def test_accept_creator_applied_requires_business_role_and_creates_collaboration(_stub_notifications):
    app_repo = FakeApplicationRepo(row=dict(APPLICATION_ROW))
    collab_repo = FakeCollaborationRepo()

    result = await application_service.accept_application(
        application_id="app1",
        profile_id="p-business",
        role="business",
        app_repo=app_repo,
        campaign_repo=FakeCampaignRepo(),
        creator_repo=FakeCreatorRepo(),
        business_repo=FakeBusinessRepo(),
        collab_repo=collab_repo,
    )

    assert result.status.value == "accepted"
    assert collab_repo.inserted["creator_id"] == "c1"
    assert collab_repo.inserted["business_id"] == "b1"
    assert collab_repo.inserted["status"] == "active"
    assert len(_stub_notifications) == 1
    assert _stub_notifications[0]["profile_id"] == "p-creator"  # creator gets notified


async def test_accept_creator_applied_rejects_creator_role():
    with pytest.raises(HTTPException) as exc:
        await application_service.accept_application(
            application_id="app1",
            profile_id="p-creator",
            role="creator",
            app_repo=FakeApplicationRepo(row=dict(APPLICATION_ROW)),
            campaign_repo=FakeCampaignRepo(),
            creator_repo=FakeCreatorRepo(),
            business_repo=FakeBusinessRepo(),
            collab_repo=FakeCollaborationRepo(),
        )
    assert exc.value.status_code == 403


async def test_accept_business_invited_lets_creator_decide(_stub_notifications):
    invited_row = {**APPLICATION_ROW, "direction": "business_invited"}
    result = await application_service.accept_application(
        application_id="app1",
        profile_id="p-creator",
        role="creator",
        app_repo=FakeApplicationRepo(row=invited_row),
        campaign_repo=FakeCampaignRepo(),
        creator_repo=FakeCreatorRepo(),
        business_repo=FakeBusinessRepo(),
        collab_repo=FakeCollaborationRepo(),
    )
    assert result.status.value == "accepted"
    assert _stub_notifications[0]["profile_id"] == "p-business"  # business gets notified


async def test_accept_rejects_already_decided_application():
    with pytest.raises(HTTPException) as exc:
        await application_service.accept_application(
            application_id="app1",
            profile_id="p-business",
            role="business",
            app_repo=FakeApplicationRepo(row={**APPLICATION_ROW, "status": "accepted"}),
            campaign_repo=FakeCampaignRepo(),
            creator_repo=FakeCreatorRepo(),
            business_repo=FakeBusinessRepo(),
            collab_repo=FakeCollaborationRepo(),
        )
    assert exc.value.status_code == 400


async def test_reject_notifies_creator_and_does_not_create_collaboration(_stub_notifications):
    result = await application_service.reject_application(
        application_id="app1",
        profile_id="p-business",
        role="business",
        app_repo=FakeApplicationRepo(row=dict(APPLICATION_ROW)),
        campaign_repo=FakeCampaignRepo(),
        creator_repo=FakeCreatorRepo(),
        business_repo=FakeBusinessRepo(),
    )
    assert result.status.value == "rejected"
    assert _stub_notifications[0]["profile_id"] == "p-creator"
    assert _stub_notifications[0]["type"].value == "application_rejected"
