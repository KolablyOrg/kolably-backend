"""
Unit tests for collaboration_service — repositories injected as fakes, no Supabase.
"""

import pytest
from fastapi import HTTPException

from app.core.crypto import encrypt_token
from app.core.enums import CampaignObjective, Platform, SubmissionType
from app.models.business import Business
from app.models.campaign import Campaign
from app.models.collaboration import Collaboration
from app.models.creator import Creator
from app.schemas.collaboration import ContentSubmitRequest, RequestRevisionRequest, RevisionNoteItem
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
        self.updated_submissions = []
        self.revision_history = []

    async def get_by_id(self, collaboration_id: str):
        return Collaboration.from_row(self._row) if self._row else None

    async def update_status(self, collaboration_id: str, data: dict):
        self.updates.append((collaboration_id, data))
        row = {**self._row, **data}
        self._row = row
        return Collaboration.from_row(row)

    async def list_submissions(self, collaboration_id: str):
        return self._submissions

    async def get_latest_submission(self, collaboration_id: str, submission_type: str):
        matches = [s for s in self._submissions if s.get("submission_type") == submission_type]
        return matches[-1] if matches else None

    async def insert_submission(self, data: dict):
        self.inserted_submissions.append(data)
        row = {
            **data,
            "id": f"sub-{len(self.inserted_submissions)}",
            "submitted_at": "2024-01-01T00:00:00+00:00",
        }
        self._submissions.append(row)
        return row

    async def update_submission(self, submission_id: str, data: dict):
        self.updated_submissions.append((submission_id, data))
        for sub in self._submissions:
            if sub["id"] == submission_id:
                sub.update(data)
                return sub
        return None

    async def list_revision_history(self, collaboration_id: str):
        return self.revision_history

    async def insert_revision_history(self, data: dict):
        row = {
            **data,
            "id": f"revision-{len(self.revision_history) + 1}",
            "created_at": "2024-01-01T00:00:00+00:00",
        }
        self.revision_history.append(row)
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


# ── submit_content — live submission phase (brand collab-management) ───
async def test_submit_content_live_requires_approved_status():
    with pytest.raises(HTTPException) as exc:
        await collaboration_service.submit_content(
            collaboration_id="collab1",
            profile_id="p-creator",
            data=ContentSubmitRequest(
                content_url="https://instagram.com/reel/live1",
                platform=Platform.INSTAGRAM,
                submission_type=SubmissionType.LIVE,
            ),
            repo=FakeCollaborationRepo(row={**COLLAB_ROW, "status": "content_submitted"}),
            creator_repo=FakeCreatorRepo(creator_id="c1"),
        )
    assert exc.value.status_code == 400


async def test_submit_content_live_transitions_to_live_submitted():
    repo = FakeCollaborationRepo(row={**COLLAB_ROW, "status": "approved"})

    result = await collaboration_service.submit_content(
        collaboration_id="collab1",
        profile_id="p-creator",
        data=ContentSubmitRequest(
            content_url="https://instagram.com/reel/live1",
            platform=Platform.INSTAGRAM,
            submission_type=SubmissionType.LIVE,
        ),
        repo=repo,
        creator_repo=FakeCreatorRepo(creator_id="c1"),
        campaign_repo=FakeCampaignRepo(campaigns=[_campaign()]),
        business_repo=FakeBusinessRepo(),
    )

    assert repo.inserted_submissions[0]["submission_type"] == "live"
    assert repo.updates == [("collab1", {"status": "live_submitted"})]
    assert result["status"] == "live_submitted"


async def test_submit_content_draft_rejected_once_approved():
    """A draft resubmission doesn't make sense once the business has already
    approved and the creator has moved on to posting live."""
    with pytest.raises(HTTPException) as exc:
        await collaboration_service.submit_content(
            collaboration_id="collab1",
            profile_id="p-creator",
            data=ContentSubmitRequest(content_url="https://instagram.com/p/abc", platform=Platform.INSTAGRAM),
            repo=FakeCollaborationRepo(row={**COLLAB_ROW, "status": "approved"}),
            creator_repo=FakeCreatorRepo(creator_id="c1"),
        )
    assert exc.value.status_code == 400


# ── request_revision ─────────────────────────────────────────────────
async def test_request_revision_transitions_status_and_stores_notes(_stub_notifications):
    repo = FakeCollaborationRepo(row={**COLLAB_ROW, "status": "content_submitted"})

    result = await collaboration_service.request_revision(
        collaboration_id="collab1",
        profile_id="p-business",
        data=RequestRevisionRequest(
            notes=[RevisionNoteItem(timestamp="0:04", note="Trim the intro")],
            overall_note="Punchier caption please",
        ),
        repo=repo,
        business_repo=FakeBusinessRepo(),
        creator_repo=FakeCreatorRepo(),
    )

    assert result["status"] == "revision_requested"
    assert result["revision_notes"] == [{"timestamp": "0:04", "note": "Trim the intro"}]
    assert result["revision_overall_note"] == "Punchier caption please"
    assert result["revision_rounds"] == 1
    assert result["revision_history"][0]["revision_number"] == 1
    assert len(_stub_notifications) == 1
    assert _stub_notifications[0]["type"].value == "revision_requested"


async def test_request_revision_rejects_when_not_submitted():
    with pytest.raises(HTTPException) as exc:
        await collaboration_service.request_revision(
            collaboration_id="collab1",
            profile_id="p-business",
            data=RequestRevisionRequest(overall_note="Fix it"),
            repo=FakeCollaborationRepo(row={**COLLAB_ROW, "status": "active"}),
            business_repo=FakeBusinessRepo(),
            creator_repo=FakeCreatorRepo(),
        )
    assert exc.value.status_code == 400


async def test_request_revision_rejects_after_free_round_is_used():
    with pytest.raises(HTTPException) as exc:
        await collaboration_service.request_revision(
            collaboration_id="collab1",
            profile_id="p-business",
            data=RequestRevisionRequest(overall_note="Fix it again"),
            repo=FakeCollaborationRepo(row={**COLLAB_ROW, "status": "content_submitted", "revision_rounds": 1}),
            business_repo=FakeBusinessRepo(),
            creator_repo=FakeCreatorRepo(),
        )
    assert exc.value.status_code == 400


async def test_request_revision_requires_at_least_one_note():
    with pytest.raises(HTTPException) as exc:
        await collaboration_service.request_revision(
            collaboration_id="collab1",
            profile_id="p-business",
            data=RequestRevisionRequest(),
            repo=FakeCollaborationRepo(row={**COLLAB_ROW, "status": "content_submitted"}),
            business_repo=FakeBusinessRepo(),
            creator_repo=FakeCreatorRepo(),
        )
    assert exc.value.status_code == 400


async def test_request_revision_rejects_non_owning_business():
    with pytest.raises(HTTPException) as exc:
        await collaboration_service.request_revision(
            collaboration_id="collab1",
            profile_id="p-other-business",
            data=RequestRevisionRequest(overall_note="Fix it"),
            repo=FakeCollaborationRepo(row={**COLLAB_ROW, "status": "content_submitted"}),
            business_repo=FakeBusinessRepo(business_id="b-other"),
            creator_repo=FakeCreatorRepo(),
        )
    assert exc.value.status_code == 403


# ── approve_draft ────────────────────────────────────────────────────
async def test_approve_draft_transitions_status():
    repo = FakeCollaborationRepo(row={**COLLAB_ROW, "status": "content_submitted"})

    result = await collaboration_service.approve_draft(
        collaboration_id="collab1",
        profile_id="p-business",
        repo=repo,
        business_repo=FakeBusinessRepo(),
    )

    assert result["status"] == "approved"
    assert repo.updates == [("collab1", {"status": "approved"})]


async def test_approve_draft_rejects_when_not_submitted():
    with pytest.raises(HTTPException) as exc:
        await collaboration_service.approve_draft(
            collaboration_id="collab1",
            profile_id="p-business",
            repo=FakeCollaborationRepo(row={**COLLAB_ROW, "status": "active"}),
            business_repo=FakeBusinessRepo(),
        )
    assert exc.value.status_code == 400


# ── verify_live_post ─────────────────────────────────────────────────
LIVE_SUBMISSION = {
    "id": "sub-live",
    "collaboration_id": "collab1",
    "content_url": "https://instagram.com/reel/live1",
    "platform": "instagram",
    "submission_type": "live",
    "submitted_at": "2024-01-01T00:00:00+00:00",
}


async def test_verify_live_post_checks_permalink_and_tag(monkeypatch):
    async def fake_fetch_media(access_token):
        return [
            {"permalink": "https://instagram.com/reel/live1", "caption": "Loved the @acme_co brunch!"},
        ]

    monkeypatch.setattr(collaboration_service.instagram_service, "fetch_media", fake_fetch_media)

    connected_creator = {**CREATOR_ROW, "instagram_access_token": encrypt_token("tok")}
    business_with_handle = {**BUSINESS_ROW, "instagram_handle": "@acme_co"}
    repo = FakeCollaborationRepo(
        row={**COLLAB_ROW, "status": "live_submitted"},
        submissions=[LIVE_SUBMISSION],
    )

    result = await collaboration_service.verify_live_post(
        collaboration_id="collab1",
        profile_id="p-business",
        repo=repo,
        business_repo=FakeBusinessRepo(row=business_with_handle),
        creator_repo=FakeCreatorRepo(row=connected_creator),
        campaign_repo=FakeCampaignRepo(campaigns=[]),
    )

    checks = result["content_submissions"][0]["verification_checks"]
    assert checks["post_live"] is True
    assert checks["tagged_business"] is True
    assert checks["paid_partnership_label"] is None  # never fabricated


async def test_verify_live_post_post_not_found(monkeypatch):
    async def fake_fetch_media(access_token):
        return [{"permalink": "https://instagram.com/reel/some-other-post", "caption": "unrelated"}]

    monkeypatch.setattr(collaboration_service.instagram_service, "fetch_media", fake_fetch_media)

    connected_creator = {**CREATOR_ROW, "instagram_access_token": encrypt_token("tok")}
    repo = FakeCollaborationRepo(
        row={**COLLAB_ROW, "status": "live_submitted"},
        submissions=[LIVE_SUBMISSION],
    )

    result = await collaboration_service.verify_live_post(
        collaboration_id="collab1",
        profile_id="p-business",
        repo=repo,
        business_repo=FakeBusinessRepo(),
        creator_repo=FakeCreatorRepo(row=connected_creator),
        campaign_repo=FakeCampaignRepo(campaigns=[]),
    )

    checks = result["content_submissions"][0]["verification_checks"]
    assert checks["post_live"] is False


async def test_verify_live_post_degrades_gracefully_without_instagram_token():
    """No token to verify with (e.g. creator disconnected Instagram since
    posting) shouldn't error out — just nothing gets auto-checked."""
    repo = FakeCollaborationRepo(
        row={**COLLAB_ROW, "status": "live_submitted"},
        submissions=[LIVE_SUBMISSION],
    )

    result = await collaboration_service.verify_live_post(
        collaboration_id="collab1",
        profile_id="p-business",
        repo=repo,
        business_repo=FakeBusinessRepo(),
        creator_repo=FakeCreatorRepo(row={**CREATOR_ROW, "instagram_access_token": None}),
        campaign_repo=FakeCampaignRepo(campaigns=[]),
    )

    checks = result["content_submissions"][0]["verification_checks"]
    assert checks == {"post_live": None, "tagged_business": None, "paid_partnership_label": None}


async def test_verify_live_post_rejects_when_not_live_submitted():
    with pytest.raises(HTTPException) as exc:
        await collaboration_service.verify_live_post(
            collaboration_id="collab1",
            profile_id="p-business",
            repo=FakeCollaborationRepo(row={**COLLAB_ROW, "status": "approved"}),
            business_repo=FakeBusinessRepo(),
            creator_repo=FakeCreatorRepo(),
        )
    assert exc.value.status_code == 400


# ── confirm_payment ──────────────────────────────────────────────────
async def test_confirm_payment_completes_collaboration(_stub_notifications):
    repo = FakeCollaborationRepo(row={**COLLAB_ROW, "status": "live_submitted"})

    result = await collaboration_service.confirm_payment(
        collaboration_id="collab1",
        profile_id="p-business",
        repo=repo,
        business_repo=FakeBusinessRepo(),
        creator_repo=FakeCreatorRepo(),
    )

    assert result["status"] == "completed"
    assert result["payment_confirmed_at"] is not None
    assert len(_stub_notifications) == 1


async def test_confirm_payment_rejects_before_live_submission():
    with pytest.raises(HTTPException) as exc:
        await collaboration_service.confirm_payment(
            collaboration_id="collab1",
            profile_id="p-business",
            repo=FakeCollaborationRepo(row={**COLLAB_ROW, "status": "approved"}),
            business_repo=FakeBusinessRepo(),
            creator_repo=FakeCreatorRepo(),
        )
    assert exc.value.status_code == 400
