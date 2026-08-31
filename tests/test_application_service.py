"""
Unit tests for application_service — repositories injected as fakes, no Supabase.
"""

import pytest
from fastapi import HTTPException

from app.models.application import CampaignApplication
from app.models.business import Business
from app.models.campaign import Campaign
from app.models.creator import Creator
from app.schemas.application import (
    ApplicationCreateRequest,
    ApplicationRevisionRequest,
    ApplicationUpdateRequest,
)
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
    def __init__(self, row=None, accepted_count: int = 0):
        self._row = row if row is not None else dict(CAMPAIGN_ROW)
        self._accepted_count = accepted_count

    async def get_by_id(self, campaign_id: str):
        return Campaign.from_row(self._row) if self._row else None

    async def fetch_application_counts(self, campaign_ids: list[str]):
        if not campaign_ids:
            return {}
        return {
            campaign_ids[0]: {
                "applicant_count": 1,
                "accepted_count": self._accepted_count,
            }
        }


class FakeApplicationRepo:
    def __init__(self, existing=None, row=None):
        self._existing = existing
        self._row = row
        self.inserted = None
        self.status_updates = []
        self.application_updates = []
        self.deleted = None

    async def get_existing(self, campaign_id, creator_id):
        return CampaignApplication.from_row(self._existing) if self._existing else None

    async def insert_application(self, data: dict):
        self.inserted = data
        row = {**data, "id": "app-new", "created_at": "2024-01-01T00:00:00+00:00"}
        return CampaignApplication.from_row(row)

    async def list_by_creator(self, creator_id: str, page: int = 1, page_size: int = 20):
        if self._row:
            return [CampaignApplication.from_row(self._row)], 1
        return [], 0

    async def get_by_id(self, application_id: str):
        return CampaignApplication.from_row(self._row) if self._row else None

    async def update_status(self, application_id: str, status: str):
        self.status_updates.append((application_id, status))
        row = {**self._row, "status": status}
        self._row = row
        return CampaignApplication.from_row(row)

    async def update_application(self, application_id: str, data: dict):
        self.application_updates.append((application_id, data))
        row = {**self._row, **data}
        self._row = row
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


@pytest.fixture(autouse=True)
def _stub_chat(monkeypatch):
    """accept_application auto-creates a conversation for the new
    collaboration — stub it out so tests don't hit the real Supabase client
    (get_or_create_conversation instantiates real repos when none are
    injected, exactly like notification_service above)."""
    calls = []

    async def _fake_get_or_create_conversation(profile_id, other_profile_id, collaboration_id, **kwargs):
        calls.append({
            "profile_id": profile_id,
            "other_profile_id": other_profile_id,
            "collaboration_id": collaboration_id,
        })
        return {"id": "conv1"}, True

    monkeypatch.setattr(
        application_service.chat_service, "get_or_create_conversation", _fake_get_or_create_conversation
    )
    return calls


async def test_apply_to_campaign_creates_pending_application_and_notifies_business(_stub_notifications):
    result = await application_service.apply_to_campaign(
        profile_id="p-creator",
        data=ApplicationCreateRequest(campaign_id="camp1", message="Pick me!"),
        # CAMPAIGN_ROW's creator_category is "food" — must qualify or this
        # happy path itself trips the new requirements gate.
        creator_repo=FakeCreatorRepo(row={**CREATOR_ROW, "niche": "food"}),
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
            creator_repo=FakeCreatorRepo(row={**CREATOR_ROW, "niche": "food"}),
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


# ── server-side requirements gate (#52 — frontend disables Apply, but a
# direct API call bypassed it entirely since nothing here re-checked) ──


async def test_apply_to_campaign_rejects_when_below_follower_minimum():
    with pytest.raises(HTTPException) as exc:
        await application_service.apply_to_campaign(
            profile_id="p-creator",
            data=ApplicationCreateRequest(campaign_id="camp1"),
            creator_repo=FakeCreatorRepo(row={**CREATOR_ROW, "niche": "food", "follower_count": 500}),
            campaign_repo=FakeCampaignRepo(row={**CAMPAIGN_ROW, "follower_range_min": 5000}),
            business_repo=FakeBusinessRepo(),
            app_repo=FakeApplicationRepo(),
        )
    assert exc.value.status_code == 400
    assert "5000 followers" in exc.value.detail


async def test_apply_to_campaign_rejects_when_below_engagement_minimum():
    with pytest.raises(HTTPException) as exc:
        await application_service.apply_to_campaign(
            profile_id="p-creator",
            data=ApplicationCreateRequest(campaign_id="camp1"),
            creator_repo=FakeCreatorRepo(row={**CREATOR_ROW, "niche": "food", "engagement_rate": 1.0}),
            campaign_repo=FakeCampaignRepo(row={**CAMPAIGN_ROW, "min_engagement_rate": 3.0}),
            business_repo=FakeBusinessRepo(),
            app_repo=FakeApplicationRepo(),
        )
    assert exc.value.status_code == 400
    assert "engagement rate" in exc.value.detail


async def test_apply_to_campaign_rejects_when_missing_required_platform_handle():
    with pytest.raises(HTTPException) as exc:
        await application_service.apply_to_campaign(
            profile_id="p-creator",
            data=ApplicationCreateRequest(campaign_id="camp1"),
            creator_repo=FakeCreatorRepo(row={**CREATOR_ROW, "niche": "food", "tiktok_handle": None}),
            campaign_repo=FakeCampaignRepo(row={**CAMPAIGN_ROW, "platforms": ["instagram", "tiktok"]}),
            business_repo=FakeBusinessRepo(),
            app_repo=FakeApplicationRepo(),
        )
    assert exc.value.status_code == 400
    assert "TikTok" in exc.value.detail


async def test_apply_to_campaign_allows_platform_requirement_when_handle_present():
    result = await application_service.apply_to_campaign(
        profile_id="p-creator",
        data=ApplicationCreateRequest(campaign_id="camp1"),
        creator_repo=FakeCreatorRepo(row={**CREATOR_ROW, "niche": "food", "tiktok_handle": "@alice"}),
        campaign_repo=FakeCampaignRepo(row={**CAMPAIGN_ROW, "platforms": ["instagram", "tiktok"]}),
        business_repo=FakeBusinessRepo(),
        app_repo=FakeApplicationRepo(),
    )
    assert result.status.value == "pending"


async def test_apply_to_campaign_rejects_when_niche_does_not_match():
    with pytest.raises(HTTPException) as exc:
        await application_service.apply_to_campaign(
            profile_id="p-creator",
            data=ApplicationCreateRequest(campaign_id="camp1"),
            creator_repo=FakeCreatorRepo(row={**CREATOR_ROW, "niche": "beauty", "categories": []}),
            campaign_repo=FakeCampaignRepo(),  # creator_category="food"
            business_repo=FakeBusinessRepo(),
            app_repo=FakeApplicationRepo(),
        )
    assert exc.value.status_code == 400
    assert "food niche" in exc.value.detail


async def test_apply_to_campaign_allows_niche_match_via_categories_not_just_niche():
    """buildRequirements() on the frontend accepts either creator.niche OR
    creator.categories containing the campaign's creator_category — a
    creator whose primary niche differs but who also tags themselves in
    the requested category still qualifies."""
    result = await application_service.apply_to_campaign(
        profile_id="p-creator",
        data=ApplicationCreateRequest(campaign_id="camp1"),
        creator_repo=FakeCreatorRepo(row={**CREATOR_ROW, "niche": "beauty", "categories": ["food", "travel"]}),
        campaign_repo=FakeCampaignRepo(),  # creator_category="food"
        business_repo=FakeBusinessRepo(),
        app_repo=FakeApplicationRepo(),
    )
    assert result.status.value == "pending"


async def test_apply_to_campaign_allows_when_campaign_sets_no_requirements():
    result = await application_service.apply_to_campaign(
        profile_id="p-creator",
        data=ApplicationCreateRequest(campaign_id="camp1"),
        creator_repo=FakeCreatorRepo(),  # no niche, no follower_count, nothing set
        campaign_repo=FakeCampaignRepo(
            row={**CAMPAIGN_ROW, "creator_category": "", "follower_range_min": None, "min_engagement_rate": None}
        ),
        business_repo=FakeBusinessRepo(),
        app_repo=FakeApplicationRepo(),
    )
    assert result.status.value == "pending"


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


async def test_accept_creator_applied_requires_business_role_and_creates_collaboration(_stub_notifications, _stub_chat):
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
    assert result.collaboration_id == "collab1"
    assert collab_repo.inserted["creator_id"] == "c1"
    assert collab_repo.inserted["business_id"] == "b1"
    assert collab_repo.inserted["status"] == "active"
    assert len(_stub_notifications) == 1
    assert _stub_notifications[0]["profile_id"] == "p-creator"  # creator gets notified

    # Accepting should auto-create the chat conversation for the new
    # collaboration — there was previously no way to message at all once a
    # collaboration started unless someone happened to have messaged before.
    assert len(_stub_chat) == 1
    assert _stub_chat[0]["profile_id"] == CREATOR_ROW["profile_id"]
    assert _stub_chat[0]["other_profile_id"] == BUSINESS_ROW["profile_id"]
    assert _stub_chat[0]["collaboration_id"] == "collab1"


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


async def test_accept_business_invited_lets_creator_decide(_stub_notifications, _stub_chat):
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


async def test_accept_rejects_when_max_creators_reached():
    with pytest.raises(HTTPException) as exc:
        await application_service.accept_application(
            application_id="app1",
            profile_id="p-business",
            role="business",
            app_repo=FakeApplicationRepo(row=dict(APPLICATION_ROW)),
            campaign_repo=FakeCampaignRepo(
                row={**CAMPAIGN_ROW, "max_creators": 2},
                accepted_count=2,
            ),
            creator_repo=FakeCreatorRepo(),
            business_repo=FakeBusinessRepo(),
            collab_repo=FakeCollaborationRepo(),
        )
    assert exc.value.status_code == 400
    assert "maximum number of creators" in exc.value.detail


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


async def test_request_revision_sets_status_and_reason(_stub_notifications):
    app_repo = FakeApplicationRepo(row=dict(APPLICATION_ROW))

    result = await application_service.request_revision(
        application_id="app1",
        profile_id="p-business",
        role="business",
        data=ApplicationRevisionRequest(reason="Please add more portfolio links"),
        app_repo=app_repo,
        campaign_repo=FakeCampaignRepo(),
        creator_repo=FakeCreatorRepo(),
        business_repo=FakeBusinessRepo(),
    )

    assert result.status.value == "revision_requested"
    assert result.revision_reason == "Please add more portfolio links"
    assert app_repo.application_updates[0][1]["status"] == "revision_requested"
    assert _stub_notifications[0]["type"].value == "revision_requested"
    assert _stub_notifications[0]["profile_id"] == "p-creator"


async def test_request_revision_rejects_creator_on_creator_applied():
    with pytest.raises(HTTPException) as exc:
        await application_service.request_revision(
            application_id="app1",
            profile_id="p-creator",
            role="creator",
            data=ApplicationRevisionRequest(reason="n/a"),
            app_repo=FakeApplicationRepo(row=dict(APPLICATION_ROW)),
            campaign_repo=FakeCampaignRepo(),
            creator_repo=FakeCreatorRepo(),
            business_repo=FakeBusinessRepo(),
        )
    assert exc.value.status_code == 403


async def test_resubmit_application_resets_to_pending(_stub_notifications):
    app_repo = FakeApplicationRepo(
        row={
            **APPLICATION_ROW,
            "status": "revision_requested",
            "revision_reason": "Need better examples",
        }
    )

    result = await application_service.resubmit_application(
        application_id="app1",
        profile_id="p-creator",
        data=ApplicationUpdateRequest(message="Updated pitch", example_content_url="https://ig.com/x"),
        creator_repo=FakeCreatorRepo(),
        business_repo=FakeBusinessRepo(),
        campaign_repo=FakeCampaignRepo(),
        app_repo=app_repo,
    )

    assert result.status.value == "pending"
    assert result.revision_reason is None
    assert result.message == "Updated pitch"
    assert _stub_notifications[0]["type"].value == "application_resubmitted"
    assert _stub_notifications[0]["profile_id"] == "p-business"


async def test_resubmit_rejects_when_not_revision_requested():
    with pytest.raises(HTTPException) as exc:
        await application_service.resubmit_application(
            application_id="app1",
            profile_id="p-creator",
            data=ApplicationUpdateRequest(message="Nope"),
            creator_repo=FakeCreatorRepo(),
            app_repo=FakeApplicationRepo(row=dict(APPLICATION_ROW)),
        )
    assert exc.value.status_code == 400


async def test_list_my_applications_returns_paginated_response():
    app_row = {
        **APPLICATION_ROW,
        "campaigns": {
            **CAMPAIGN_ROW,
            "businesses": {
                "id": "b1",
                "business_name": "Acme Co",
                "logo_url": "https://img.com/logo.jpg",
            },
        },
    }
    app_repo = FakeApplicationRepo(row=app_row)
    res = await application_service.list_my_applications(
        profile_id="p-creator",
        creator_repo=FakeCreatorRepo(),
        app_repo=app_repo,
    )
    assert res["total"] == 1
    assert len(res["items"]) == 1
    item = res["items"][0]
    assert item.id == "app1"
    assert item.campaign.title == "Summer Campaign"
    assert item.business.business_name == "Acme Co"
    assert item.business.logo_url == "https://img.com/logo.jpg"

