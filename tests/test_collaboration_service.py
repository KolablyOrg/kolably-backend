"""
Unit tests for collaboration_service — repositories injected as fakes, no Supabase.
"""

import pytest
from fastapi import HTTPException

from app.models.business import Business
from app.models.collaboration import Collaboration
from app.models.creator import Creator
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
    def __init__(self, row=None):
        self._row = row if row is not None else dict(COLLAB_ROW)
        self.updates = []

    async def get_by_id(self, collaboration_id: str):
        return Collaboration.from_row(self._row) if self._row else None

    async def update_status(self, collaboration_id: str, data: dict):
        self.updates.append((collaboration_id, data))
        row = {**self._row, **data}
        return Collaboration.from_row(row)


class FakeBusinessRepo:
    def __init__(self, business_id="b1", row=None):
        self._business_id = business_id
        self._row = row or dict(BUSINESS_ROW)

    async def get_id_by_profile_id(self, profile_id: str):
        return self._business_id

    async def get_by_id(self, business_id: str):
        return Business.from_row(self._row) if self._row else None


class FakeCreatorRepo:
    def __init__(self, row=None):
        self._row = row or dict(CREATOR_ROW)

    async def get_by_id(self, creator_id: str):
        return Creator.from_row(self._row) if self._row else None


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
