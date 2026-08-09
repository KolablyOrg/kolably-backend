"""
Unit tests for collaboration_service — repositories injected as fakes, no Supabase.
"""

import pytest
from fastapi import HTTPException

from app.core.enums import CampaignObjective, Platform
from app.models.business import Business
from app.models.campaign import Campaign
from app.models.collaboration import Collaboration
from app.models.creator import Creator
from app.schemas.collaboration import ContentSubmitRequest
from app.services import collaboration_service

COLLAB_ROW = {
    "id": "collab1",
    "campaign_id": "camp1",
    "creator_id": "c1",
    "business_id": "b1",
    "status": "active",
    "created_at": "2024-01-01T00:00:00+00:00",
    "completed_at": None,
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


class FakeCollaborationRepo:
    def __init__(self, row=None, submissions=None):
        self._row = row if row is not None else dict(COLLAB_ROW)
        self._submissions = list(submissions or [])
        self.updates = []
        self.inserted_submissions = []

    async def get_by_id(self, collaboration_id: str):
        return Collaboration.from_row(self._row) if self._row else None

    async def update_status(self, collaboration_id: str, data: dict):
        self.updates.append((collaboration_id, data))
        row = {**self._row, **data}
        self._row = row
        return Collaboration.from_row(row)

    async def list_submissions(self, collaboration_id: str):
        return self._submissions

    async def insert_submission(self, data: dict):
        self.inserted_submissions.append(data)
        row = {**data, "id": "sub-new", "submitted_at": "2024-01-01T00:00:00+00:00"}
        return row


class FakeCampaignRepo:
    def __init__(self, campaigns=None):
        self._campaigns = {c.id: c for c in (campaigns or [])}

    async def get_by_id(self, campaign_id: str):
        return self._campaigns.get(campaign_id)

    async def get_by_ids(self, campaign_ids):
        return [c for cid, c in self._campaigns.items() if cid in campaign_ids]


class FakeBusinessRepo:
    def __init__(self, business_id="b1", row=None):
        self._business_id = business_id
        self._row = row or dict(BUSINESS_ROW)

    async def get_id_by_profile_id(self, profile_id: str):
        return self._business_id

    async def get_by_id(self, business_id: str):
        return Business.from_row(self._row) if self._row else None

    async def get_by_ids(self, business_ids):
        biz = Business.from_row(self._row) if self._row else None
        return [biz] if biz and biz.id in business_ids else []


class FakeCreatorRepo:
    def __init__(self, row=None, creator_id="c1"):
        self._row = row or dict(CREATOR_ROW)
        self._creator_id = creator_id

    async def get_by_id(self, creator_id: str):
        return Creator.from_row(self._row) if self._row else None

    async def get_id_by_profile_id(self, profile_id: str):
        return self._creator_id


@pytest.fixture(autouse=True)
def _stub_notifications(monkeypatch):
    sent = []

    async def _fake_create_notification(profile_id, type, title, body, related_id=None, **kwargs):
        sent.append({"profile_id": profile_id, "type": type})

    monkeypatch.setattr(collaboration_service.notification_service, "create_notification", _fake_create_notification)
    return sent


async def test_complete_collaboration_transitions_status_and_notifies_creator(_stub_notifications):
    repo = FakeCollaborationRepo()

    result = await collaboration_service.complete_collaboration(
        collaboration_id="collab1",
        profile_id="p-business",
        repo=repo,
        business_repo=FakeBusinessRepo(),
        creator_repo=FakeCreatorRepo(),
    )

    assert result["status"] == "completed"
    assert result["completed_at"] is not None
    assert len(_stub_notifications) == 1
    assert _stub_notifications[0]["profile_id"] == "p-creator"


async def test_complete_collaboration_rejects_non_owning_business():
    with pytest.raises(HTTPException) as exc:
        await collaboration_service.complete_collaboration(
            collaboration_id="collab1",
            profile_id="p-other-business",
            repo=FakeCollaborationRepo(),
            business_repo=FakeBusinessRepo(business_id="b-other"),
            creator_repo=FakeCreatorRepo(),
        )
    assert exc.value.status_code == 403


async def test_complete_collaboration_rejects_already_completed():
    with pytest.raises(HTTPException) as exc:
        await collaboration_service.complete_collaboration(
            collaboration_id="collab1",
            profile_id="p-business",
            repo=FakeCollaborationRepo(row={**COLLAB_ROW, "status": "completed"}),
            business_repo=FakeBusinessRepo(),
            creator_repo=FakeCreatorRepo(),
        )
    assert exc.value.status_code == 400


async def test_cancel_collaboration_transitions_status():
    repo = FakeCollaborationRepo()

    result = await collaboration_service.cancel_collaboration(
        collaboration_id="collab1",
        profile_id="p-business",
        repo=repo,
        business_repo=FakeBusinessRepo(),
    )

    assert result["status"] == "cancelled"
    assert repo.updates == [("collab1", {"status": "cancelled"})]


async def test_cancel_collaboration_rejects_non_owning_business():
    with pytest.raises(HTTPException) as exc:
        await collaboration_service.cancel_collaboration(
            collaboration_id="collab1",
            profile_id="p-other-business",
            repo=FakeCollaborationRepo(),
            business_repo=FakeBusinessRepo(business_id="b-other"),
        )
    assert exc.value.status_code == 403


def _campaign(**overrides):
    defaults = dict(
        id="camp1",
        business_id="b1",
        title="Brunch launch",
        objective=CampaignObjective.BRAND_AWARENESS,
        description="Desc",
    )
    return Campaign(**{**defaults, **overrides})


# ── get_collaboration / list_collaborations — campaign+business joins ──
async def test_get_collaboration_includes_campaign_and_business_join():
    result = await collaboration_service.get_collaboration(
        "collab1",
        repo=FakeCollaborationRepo(),
        campaign_repo=FakeCampaignRepo(campaigns=[_campaign()]),
        business_repo=FakeBusinessRepo(),
    )

    assert result["campaign_title"] == "Brunch launch"
    assert result["business_name"] == "Acme Co"
    assert result["campaign"]["title"] == "Brunch launch"
    assert result["business"]["business_name"] == "Acme Co"


async def test_get_collaboration_join_fields_null_when_campaign_missing():
    async def _no_business(business_id):
        return None

    business_repo = FakeBusinessRepo()
    business_repo.get_by_id = _no_business

    result = await collaboration_service.get_collaboration(
        "collab1",
        repo=FakeCollaborationRepo(),
        campaign_repo=FakeCampaignRepo(campaigns=[]),
        business_repo=business_repo,
    )

    assert result["campaign_title"] is None
    assert result["campaign"] is None
    assert result["business"] is None


async def test_list_collaborations_batches_joins_across_items():
    repo = FakeCollaborationRepo()

    async def fake_list_by_creator(creator_id, page, page_size, campaign_id=None):
        return [Collaboration.from_row(COLLAB_ROW)], 1

    repo.list_by_creator = fake_list_by_creator

    result = await collaboration_service.list_collaborations(
        profile_id="p-creator",
        role="creator",
        repo=repo,
        creator_repo=FakeCreatorRepo(),
        campaign_repo=FakeCampaignRepo(campaigns=[_campaign()]),
        business_repo=FakeBusinessRepo(),
    )

    assert result["items"][0]["campaign_title"] == "Brunch launch"
    assert result["items"][0]["business_name"] == "Acme Co"


# ── submit_content ──────────────────────────────────────────────────
async def test_submit_content_inserts_submission_and_transitions_status():
    repo = FakeCollaborationRepo()

    result = await collaboration_service.submit_content(
        collaboration_id="collab1",
        profile_id="p-creator",
        data=ContentSubmitRequest(content_url="https://instagram.com/p/abc", platform=Platform.INSTAGRAM),
        repo=repo,
        creator_repo=FakeCreatorRepo(creator_id="c1"),
        campaign_repo=FakeCampaignRepo(campaigns=[_campaign()]),
        business_repo=FakeBusinessRepo(),
    )

    assert repo.inserted_submissions[0]["content_url"] == "https://instagram.com/p/abc"
    assert repo.inserted_submissions[0]["platform"] == "instagram"
    assert repo.updates == [("collab1", {"status": "content_submitted"})]
    assert result["status"] == "content_submitted"


async def test_submit_content_does_not_retransition_when_already_submitted():
    repo = FakeCollaborationRepo(row={**COLLAB_ROW, "status": "content_submitted"})

    await collaboration_service.submit_content(
        collaboration_id="collab1",
        profile_id="p-creator",
        data=ContentSubmitRequest(content_url="https://instagram.com/p/second", platform=Platform.INSTAGRAM),
        repo=repo,
        creator_repo=FakeCreatorRepo(creator_id="c1"),
        campaign_repo=FakeCampaignRepo(campaigns=[_campaign()]),
        business_repo=FakeBusinessRepo(),
    )

    assert repo.updates == []
    assert len(repo.inserted_submissions) == 1


async def test_submit_content_rejects_non_owning_creator():
    with pytest.raises(HTTPException) as exc:
        await collaboration_service.submit_content(
            collaboration_id="collab1",
            profile_id="p-other-creator",
            data=ContentSubmitRequest(content_url="https://instagram.com/p/abc", platform=Platform.INSTAGRAM),
            repo=FakeCollaborationRepo(),
            creator_repo=FakeCreatorRepo(creator_id="c-other"),
        )
    assert exc.value.status_code == 403


async def test_submit_content_rejects_completed_collaboration():
    with pytest.raises(HTTPException) as exc:
        await collaboration_service.submit_content(
            collaboration_id="collab1",
            profile_id="p-creator",
            data=ContentSubmitRequest(content_url="https://instagram.com/p/abc", platform=Platform.INSTAGRAM),
            repo=FakeCollaborationRepo(row={**COLLAB_ROW, "status": "completed"}),
            creator_repo=FakeCreatorRepo(creator_id="c1"),
        )
    assert exc.value.status_code == 400
