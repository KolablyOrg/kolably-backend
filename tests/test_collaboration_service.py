"""
Unit tests for collaboration_service — repositories injected as fakes, no Supabase.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from app.core.crypto import encrypt_token
from app.core.enums import CampaignObjective, ContentType, Platform, SubmissionType
from app.models.business import Business
from app.models.campaign import Campaign, CampaignDeliverable
from app.models.collaboration import Collaboration
from app.models.creator import Creator
from app.schemas.collaboration import (
    ApproveSubmissionRequest,
    ContentSubmitRequest,
    RequestRevisionRequest,
    RevisionNoteItem,
)
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
        # Only used by the auto-confirm sweep tests.
        self.stale_rows = []
        self.cutoffs_requested = []

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

    async def list_awaiting_creator_confirmation_before(self, cutoff):
        """Mirrors the real repo's filter (status + payment_confirmed_at <
        cutoff) rather than returning everything — otherwise a test would
        pass even if the service asked for the wrong cutoff."""
        self.cutoffs_requested.append(cutoff)
        out = []
        for row in self.stale_rows:
            if row.get("status") != "payment_confirmed":
                continue
            confirmed_at = row.get("payment_confirmed_at")
            if confirmed_at and datetime.fromisoformat(confirmed_at) < cutoff:
                out.append(Collaboration.from_row(row))
        return out

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

    async def get_by_ids(self, creator_ids):
        creator = Creator.from_row(self._row) if self._row else None
        return [creator] if creator and creator.id in creator_ids else []


class FakeMemberRepo:
    async def get_active_by_profile_id(self, profile_id):
        return None

    async def get_active_membership(self, business_id, profile_id):
        return None


async def _active_member(role):
    from types import SimpleNamespace

    return SimpleNamespace(role=role)


class FakeInvoiceRepo:
    def __init__(self, row=None):
        self._row = row
        self.status_updates = []

    async def get_by_collaboration_id(self, collaboration_id):
        from app.models.invoice import Invoice

        return Invoice.from_row(self._row) if self._row else None

    async def update_status(self, invoice_id, data):
        from app.models.invoice import Invoice

        self.status_updates.append((invoice_id, data))
        self._row = {**self._row, **data}
        return Invoice.from_row(self._row)


class FailingInvoiceRepo(FakeInvoiceRepo):
    async def update_status(self, invoice_id, data):
        self.status_updates.append((invoice_id, data))
        return None


@pytest.fixture(autouse=True)
def _stub_notifications(monkeypatch):
    sent = []

    async def _fake_create_notification(profile_id, type, title, body, related_id=None, **kwargs):
        sent.append({"profile_id": profile_id, "type": type})

    monkeypatch.setattr(collaboration_service.notification_service, "create_notification", _fake_create_notification)
    return sent


async def test_complete_collaboration_transitions_status_and_notifies_creator(_stub_notifications):
    repo = FakeCollaborationRepo(row={**COLLAB_ROW, "status": "live_submitted"})

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


async def test_complete_collaboration_rejects_before_live_post_submitted():
    """Regression: /complete is a second path to COMPLETED alongside
    confirm_payment, and without this same precondition it let a business
    skip draft approval and live-post submission entirely."""
    with pytest.raises(HTTPException) as exc:
        await collaboration_service.complete_collaboration(
            collaboration_id="collab1",
            profile_id="p-business",
            repo=FakeCollaborationRepo(row={**COLLAB_ROW, "status": "approved"}),
            business_repo=FakeBusinessRepo(),
            creator_repo=FakeCreatorRepo(),
        )
    assert exc.value.status_code == 400


async def test_complete_collaboration_rejects_non_owning_business():
    with pytest.raises(HTTPException) as exc:
        await collaboration_service.complete_collaboration(
            collaboration_id="collab1",
            profile_id="p-other-business",
            repo=FakeCollaborationRepo(row={**COLLAB_ROW, "status": "live_submitted"}),
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
        profile_id="p-business",
        role="business",
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

    # The join-fetch's business lookup is deliberately nerfed above (that's
    # what this test is exercising), which would also starve the new
    # business_access authorization check of an "owner" match — grant access
    # via a fake team membership instead, so this test stays about the join
    # fields rather than incidentally testing authorization.
    member_repo = FakeMemberRepo()
    member_repo.get_active_membership = lambda business_id, profile_id: _active_member("editor")

    result = await collaboration_service.get_collaboration(
        "collab1",
        profile_id="p-business",
        role="business",
        repo=FakeCollaborationRepo(),
        campaign_repo=FakeCampaignRepo(campaigns=[]),
        business_repo=business_repo,
        member_repo=member_repo,
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
    assert result["items"][0]["creator_name"] == "Alice"


# ── submit_content ──────────────────────────────────────────────────
async def test_submit_content_inserts_submission_and_transitions_status(_stub_notifications):
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
    assert _stub_notifications[0]["profile_id"] == "p-business"
    assert _stub_notifications[0]["type"].value == "collaboration_content_submitted"


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


async def test_submit_content_live_transitions_to_live_submitted(_stub_notifications):
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
    assert _stub_notifications[0]["profile_id"] == "p-business"
    assert _stub_notifications[0]["type"].value == "collaboration_content_submitted"


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
    repo = FakeCollaborationRepo(
        row={**COLLAB_ROW, "status": "content_submitted"},
        submissions=[dict(DRAFT_SUBMISSION)],
    )

    result = await collaboration_service.request_revision(
        collaboration_id="collab1",
        profile_id="p-business",
        data=RequestRevisionRequest(
            submission_id="sub-draft",
            notes=[RevisionNoteItem(timestamp="0:04", note="Trim the intro")],
            overall_note="Punchier caption please",
        ),
        repo=repo,
        business_repo=FakeBusinessRepo(),
        creator_repo=FakeCreatorRepo(),
        campaign_repo=FakeCampaignRepo(campaigns=[]),
    )

    assert result["status"] == "content_submitted"
    assert result["revision_notes"] == [{"timestamp": "0:04", "note": "Trim the intro"}]
    assert result["revision_overall_note"] == "Punchier caption please"
    assert result["revision_rounds"] == 1
    assert result["revision_history"][0]["revision_number"] == 1
    assert repo.updated_submissions[0][1]["draft_status"] == "needs_revision"
    assert len(_stub_notifications) == 1
    assert _stub_notifications[0]["type"].value == "revision_requested"


async def test_request_revision_rejects_when_not_submitted():
    with pytest.raises(HTTPException) as exc:
        await collaboration_service.request_revision(
            collaboration_id="collab1",
            profile_id="p-business",
            data=RequestRevisionRequest(submission_id="sub-draft", overall_note="Fix it"),
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
            data=RequestRevisionRequest(submission_id="sub-draft", overall_note="Fix it again"),
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
            data=RequestRevisionRequest(submission_id="sub-draft"),
            repo=FakeCollaborationRepo(
                row={**COLLAB_ROW, "status": "content_submitted"},
                submissions=[dict(DRAFT_SUBMISSION)],
            ),
            business_repo=FakeBusinessRepo(),
            creator_repo=FakeCreatorRepo(),
            campaign_repo=FakeCampaignRepo(campaigns=[]),
        )
    assert exc.value.status_code == 400


def test_revision_note_rejects_invalid_timestamp_format():
    with pytest.raises(ValueError):
        RevisionNoteItem(timestamp="4:75", note="Trim the intro")


async def test_request_revision_rejects_non_owning_business():
    with pytest.raises(HTTPException) as exc:
        await collaboration_service.request_revision(
            collaboration_id="collab1",
            profile_id="p-other-business",
            data=RequestRevisionRequest(submission_id="sub-draft", overall_note="Fix it"),
            repo=FakeCollaborationRepo(row={**COLLAB_ROW, "status": "content_submitted"}),
            business_repo=FakeBusinessRepo(business_id="b-other"),
            creator_repo=FakeCreatorRepo(),
        )
    assert exc.value.status_code == 403


# ── approve_draft ────────────────────────────────────────────────────
async def test_approve_draft_transitions_status(_stub_notifications):
    repo = FakeCollaborationRepo(
        row={**COLLAB_ROW, "status": "content_submitted"},
        submissions=[dict(DRAFT_SUBMISSION)],
    )

    result = await collaboration_service.approve_draft(
        collaboration_id="collab1",
        profile_id="p-business",
        data=ApproveSubmissionRequest(submission_id="sub-draft"),
        repo=repo,
        business_repo=FakeBusinessRepo(),
        creator_repo=FakeCreatorRepo(),
        campaign_repo=FakeCampaignRepo(campaigns=[]),
    )

    assert result["status"] == "approved"
    assert repo.updated_submissions[0][1]["draft_status"] == "approved"
    assert ("collab1", {"status": "approved"}) in repo.updates
    assert _stub_notifications[0]["profile_id"] == "p-creator"
    assert _stub_notifications[0]["type"].value == "collaboration_draft_approved"


async def test_approve_draft_recovers_from_prematurely_approved_status():
    two_piece_campaign = _campaign(
        deliverables=[
            CampaignDeliverable(
                platform=Platform.INSTAGRAM,
                content_type=ContentType.REEL,
                quantity=1,
            ),
            CampaignDeliverable(
                platform=Platform.INSTAGRAM,
                content_type=ContentType.STORY,
                quantity=1,
            ),
        ],
    )
    repo = FakeCollaborationRepo(
        row={**COLLAB_ROW, "status": "approved"},
        submissions=[
            {**DRAFT_SUBMISSION, "draft_status": "approved", "deliverable_index": 0},
            {
                **DRAFT_SUBMISSION,
                "id": "sub-draft-2",
                "deliverable_index": 1,
                "draft_status": "pending",
                "content_type": "story",
            },
        ],
    )

    result = await collaboration_service.approve_draft(
        collaboration_id="collab1",
        profile_id="p-business",
        data=ApproveSubmissionRequest(submission_id="sub-draft-2"),
        repo=repo,
        business_repo=FakeBusinessRepo(),
        creator_repo=FakeCreatorRepo(),
        campaign_repo=FakeCampaignRepo(campaigns=[two_piece_campaign]),
    )

    assert result["status"] == "approved"
    assert ("collab1", {"status": "content_submitted"}) in repo.updates
    assert repo.updated_submissions[-1][1]["draft_status"] == "approved"


async def test_approve_draft_rejects_when_not_submitted():
    with pytest.raises(HTTPException) as exc:
        await collaboration_service.approve_draft(
            collaboration_id="collab1",
            profile_id="p-business",
            data=ApproveSubmissionRequest(submission_id="sub-draft"),
            repo=FakeCollaborationRepo(row={**COLLAB_ROW, "status": "active"}),
            business_repo=FakeBusinessRepo(),
            campaign_repo=FakeCampaignRepo(campaigns=[]),
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

DRAFT_SUBMISSION = {
    "id": "sub-draft",
    "collaboration_id": "collab1",
    "content_url": "https://instagram.com/reel/draft1",
    "platform": "instagram",
    "submission_type": "draft",
    "content_type": "reel",
    "deliverable_index": 0,
    "draft_status": "pending",
    "submitted_at": "2024-01-01T00:00:00+00:00",
}


async def test_verify_live_post_checks_permalink_and_tag(monkeypatch, _stub_notifications):
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
    assert _stub_notifications[0]["profile_id"] == "p-creator"
    assert _stub_notifications[0]["type"].value == "collaboration_live_verified"


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
async def test_confirm_payment_does_not_complete_collaboration(_stub_notifications):
    """The business paying is only half the handshake.

    This used to write `completed` directly, which is what let a brand close
    a collaboration out permanently on its own say-so — the creator had no
    say and nothing evidenced the money actually arrived. It must now stop
    at `payment_confirmed` and leave `completed_at` unset.
    """
    repo = FakeCollaborationRepo(row={**COLLAB_ROW, "status": "live_submitted"})

    result = await collaboration_service.confirm_payment(
        collaboration_id="collab1",
        profile_id="p-business",
        repo=repo,
        business_repo=FakeBusinessRepo(),
        creator_repo=FakeCreatorRepo(),
        invoice_repo=FakeInvoiceRepo(),
    )

    assert result["status"] == "payment_confirmed"
    assert result["payment_confirmed_at"] is not None
    assert result["completed_at"] is None
    assert result["creator_confirmed_at"] is None
    # The creator is asked to act, so this must be the ask-the-creator type,
    # not the generic "it's done" one.
    assert len(_stub_notifications) == 1
    assert _stub_notifications[0]["type"].value == "collaboration_payment_confirmed"
    assert _stub_notifications[0]["profile_id"] == "p-creator"


# ── confirm_completion (creator side) ─────────────────────────────────
async def test_confirm_completion_closes_collaboration(_stub_notifications):
    repo = FakeCollaborationRepo(
        row={
            **COLLAB_ROW,
            "status": "payment_confirmed",
            "payment_confirmed_at": "2024-01-01T00:00:00+00:00",
        }
    )

    result = await collaboration_service.confirm_completion(
        collaboration_id="collab1",
        profile_id="p-creator",
        repo=repo,
        creator_repo=FakeCreatorRepo(),
        business_repo=FakeBusinessRepo(),
    )

    assert result["status"] == "completed"
    assert result["creator_confirmed_at"] is not None
    assert result["completed_at"] is not None
    # The business is the one told about it — the creator just did it.
    assert len(_stub_notifications) == 1
    assert _stub_notifications[0]["profile_id"] == "p-business"


async def test_confirm_completion_rejects_before_payment_confirmed():
    """A creator can't close a collaboration the brand hasn't paid for —
    otherwise the handshake could be short-circuited from the other side."""
    with pytest.raises(HTTPException) as exc:
        await collaboration_service.confirm_completion(
            collaboration_id="collab1",
            profile_id="p-creator",
            repo=FakeCollaborationRepo(row={**COLLAB_ROW, "status": "live_submitted"}),
            creator_repo=FakeCreatorRepo(),
            business_repo=FakeBusinessRepo(),
        )
    assert exc.value.status_code == 400


async def test_confirm_completion_rejects_non_owning_creator():
    with pytest.raises(HTTPException) as exc:
        await collaboration_service.confirm_completion(
            collaboration_id="collab1",
            profile_id="p-other-creator",
            repo=FakeCollaborationRepo(row={**COLLAB_ROW, "status": "payment_confirmed"}),
            creator_repo=FakeCreatorRepo(creator_id="c-other"),
            business_repo=FakeBusinessRepo(),
        )
    assert exc.value.status_code == 403


async def test_confirm_completion_rejects_already_completed():
    with pytest.raises(HTTPException) as exc:
        await collaboration_service.confirm_completion(
            collaboration_id="collab1",
            profile_id="p-creator",
            repo=FakeCollaborationRepo(row={**COLLAB_ROW, "status": "completed"}),
            creator_repo=FakeCreatorRepo(),
            business_repo=FakeBusinessRepo(),
        )
    assert exc.value.status_code == 400


# ── payment_confirmed is not an open collaboration ────────────────────
async def test_cancel_rejected_once_payment_confirmed():
    """Cancelling after payment would strand the creator: closed as
    cancelled, money already sent, and no completed record to invoice or
    review against."""
    with pytest.raises(HTTPException) as exc:
        await collaboration_service.cancel_collaboration(
            collaboration_id="collab1",
            profile_id="p-business",
            repo=FakeCollaborationRepo(row={**COLLAB_ROW, "status": "payment_confirmed"}),
            business_repo=FakeBusinessRepo(),
        )
    assert exc.value.status_code == 400


async def test_submit_content_rejected_once_payment_confirmed():
    with pytest.raises(HTTPException) as exc:
        await collaboration_service.submit_content(
            collaboration_id="collab1",
            profile_id="p-creator",
            data=ContentSubmitRequest(
                content_url="https://instagram.com/p/late",
                platform=Platform.INSTAGRAM,
            ),
            repo=FakeCollaborationRepo(row={**COLLAB_ROW, "status": "payment_confirmed"}),
            creator_repo=FakeCreatorRepo(),
            business_repo=FakeBusinessRepo(),
            campaign_repo=FakeCampaignRepo(campaigns=[]),
        )
    assert exc.value.status_code == 400


async def test_confirm_payment_marks_existing_invoice_paid(_stub_notifications):
    repo = FakeCollaborationRepo(row={**COLLAB_ROW, "status": "live_submitted"})
    invoice_repo = FakeInvoiceRepo(
        {
            "id": "inv1",
            "collaboration_id": "collab1",
            "creator_id": "c1",
            "business_id": "b1",
            "status": "sent",
            "created_at": "2024-01-01T00:00:00+00:00",
        }
    )

    result = await collaboration_service.confirm_payment(
        collaboration_id="collab1",
        profile_id="p-business",
        repo=repo,
        business_repo=FakeBusinessRepo(),
        creator_repo=FakeCreatorRepo(),
        invoice_repo=invoice_repo,
    )

    assert result["payment_confirmed_by"] == "p-business"
    assert invoice_repo.status_updates[0][1]["status"] == "paid"
    assert invoice_repo.status_updates[0][1]["paid_by"] == "p-business"
    assert invoice_repo.status_updates[0][1]["paid_at"] == result["payment_confirmed_at"]


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


async def test_collaboration_lifecycle_runs_from_draft_to_payment(_stub_notifications):
    repo = FakeCollaborationRepo()
    creator_repo = FakeCreatorRepo()
    business_repo = FakeBusinessRepo()
    invoice_repo = FakeInvoiceRepo()

    draft = await collaboration_service.submit_content(
        collaboration_id="collab1",
        profile_id="p-creator",
        data=ContentSubmitRequest(
            content_url="https://instagram.com/p/draft",
            platform=Platform.INSTAGRAM,
        ),
        repo=repo,
        creator_repo=creator_repo,
        business_repo=business_repo,
        campaign_repo=FakeCampaignRepo(campaigns=[]),
    )
    approved = await collaboration_service.approve_draft(
        collaboration_id="collab1",
        profile_id="p-business",
        data=ApproveSubmissionRequest(submission_id=draft["content_submissions"][0]["id"]),
        repo=repo,
        business_repo=business_repo,
        creator_repo=creator_repo,
        campaign_repo=FakeCampaignRepo(campaigns=[]),
    )
    live = await collaboration_service.submit_content(
        collaboration_id="collab1",
        profile_id="p-creator",
        data=ContentSubmitRequest(
            content_url="https://instagram.com/reel/live",
            platform=Platform.INSTAGRAM,
            submission_type=SubmissionType.LIVE,
        ),
        repo=repo,
        creator_repo=creator_repo,
        business_repo=business_repo,
        campaign_repo=FakeCampaignRepo(campaigns=[]),
    )
    verified = await collaboration_service.verify_live_post(
        collaboration_id="collab1",
        profile_id="p-business",
        repo=repo,
        business_repo=business_repo,
        creator_repo=creator_repo,
        campaign_repo=FakeCampaignRepo(campaigns=[]),
    )
    paid = await collaboration_service.confirm_payment(
        collaboration_id="collab1",
        profile_id="p-business",
        repo=repo,
        business_repo=business_repo,
        creator_repo=creator_repo,
        invoice_repo=invoice_repo,
    )

    confirmed = await collaboration_service.confirm_completion(
        collaboration_id="collab1",
        profile_id="p-creator",
        repo=repo,
        creator_repo=creator_repo,
        business_repo=business_repo,
    )

    assert [
        draft["status"],
        approved["status"],
        live["status"],
        verified["status"],
        paid["status"],
        confirmed["status"],
    ] == [
        "content_submitted",
        "approved",
        "live_submitted",
        "live_submitted",
        # Paying no longer ends it — the creator's confirmation does.
        "payment_confirmed",
        "completed",
    ]
    assert [notification["type"].value for notification in _stub_notifications] == [
        "collaboration_content_submitted",
        "collaboration_draft_approved",
        "collaboration_content_submitted",
        "collaboration_live_verified",
        "collaboration_payment_confirmed",
        "collaboration_completed",
    ]


async def test_confirm_payment_rejects_duplicate_confirmation():
    with pytest.raises(HTTPException) as exc:
        await collaboration_service.confirm_payment(
            collaboration_id="collab1",
            profile_id="p-business",
            repo=FakeCollaborationRepo(row={**COLLAB_ROW, "status": "completed"}),
            business_repo=FakeBusinessRepo(),
            creator_repo=FakeCreatorRepo(),
            invoice_repo=FakeInvoiceRepo(),
        )
    assert exc.value.status_code == 400


async def test_confirm_payment_surfaces_invoice_sync_failure():
    with pytest.raises(HTTPException) as exc:
        await collaboration_service.confirm_payment(
            collaboration_id="collab1",
            profile_id="p-business",
            repo=FakeCollaborationRepo(row={**COLLAB_ROW, "status": "live_submitted"}),
            business_repo=FakeBusinessRepo(),
            creator_repo=FakeCreatorRepo(),
            invoice_repo=FailingInvoiceRepo(
                {
                    "id": "inv1",
                    "collaboration_id": "collab1",
                    "creator_id": "c1",
                    "business_id": "b1",
                    "status": "sent",
                    "created_at": "2024-01-01T00:00:00+00:00",
                }
            ),
        )
    assert exc.value.status_code == 500


# ── auto-confirm sweep ────────────────────────────────────────────────
def _stale_row(collab_id: str, days_ago: float):
    return {
        **COLLAB_ROW,
        "id": collab_id,
        "status": "payment_confirmed",
        "payment_confirmed_at": (datetime.now(UTC) - timedelta(days=days_ago)).isoformat(),
    }


async def test_auto_confirm_closes_collaborations_past_the_grace_window(_stub_notifications):
    repo = FakeCollaborationRepo()
    repo.stale_rows = [_stale_row("collab-stale", days_ago=8)]

    result = await collaboration_service.auto_confirm_stale_collaborations(
        repo=repo,
        creator_repo=FakeCreatorRepo(),
        business_repo=FakeBusinessRepo(),
    )

    assert result == {"candidates": 1, "closed": 1, "failed": 0}
    _, update = repo.updates[0]
    assert update["status"] == "completed"
    assert update["completed_at"] is not None
    # creator_confirmed_at must stay unset: nobody actually confirmed, and
    # writing a confirmation the creator never gave would misrepresent it.
    assert "creator_confirmed_at" not in update
    # Both sides are told, so neither is surprised by a closed collaboration.
    assert {n["profile_id"] for n in _stub_notifications} == {"p-creator", "p-business"}


async def test_auto_confirm_leaves_collaborations_inside_the_grace_window():
    repo = FakeCollaborationRepo()
    repo.stale_rows = [_stale_row("collab-fresh", days_ago=3)]

    result = await collaboration_service.auto_confirm_stale_collaborations(
        repo=repo,
        creator_repo=FakeCreatorRepo(),
        business_repo=FakeBusinessRepo(),
    )

    assert result == {"candidates": 0, "closed": 0, "failed": 0}
    assert repo.updates == []


async def test_auto_confirm_uses_a_seven_day_cutoff():
    """Pins the window itself. A silent change to the constant would
    otherwise close collaborations earlier than the copy shown to creators
    in the confirm-payment notification promises."""
    repo = FakeCollaborationRepo()

    await collaboration_service.auto_confirm_stale_collaborations(
        repo=repo,
        creator_repo=FakeCreatorRepo(),
        business_repo=FakeBusinessRepo(),
    )

    requested = repo.cutoffs_requested[0]
    expected = datetime.now(UTC) - timedelta(days=7)
    assert abs((requested - expected).total_seconds()) < 60


async def test_auto_confirm_keeps_going_when_one_row_fails(_stub_notifications):
    """One bad row must not abort the sweep — otherwise a single broken
    collaboration blocks every other one from ever being closed."""

    class PartiallyFailingRepo(FakeCollaborationRepo):
        async def update_status(self, collaboration_id, data):
            if collaboration_id == "collab-bad":
                raise RuntimeError("row is wedged")
            return await super().update_status(collaboration_id, data)

    repo = PartiallyFailingRepo()
    repo.stale_rows = [
        _stale_row("collab-bad", days_ago=9),
        _stale_row("collab-good", days_ago=9),
    ]

    result = await collaboration_service.auto_confirm_stale_collaborations(
        repo=repo,
        creator_repo=FakeCreatorRepo(),
        business_repo=FakeBusinessRepo(),
    )

    assert result == {"candidates": 2, "closed": 1, "failed": 1}
    assert [collab_id for collab_id, _ in repo.updates] == ["collab-good"]
