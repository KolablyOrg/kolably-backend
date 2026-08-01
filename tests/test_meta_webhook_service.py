"""
Unit tests for meta_webhook_service.handle_data_deletion — repos are faked,
no real Supabase calls happen.
"""

import base64
import hashlib
import hmac
import json

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.models.creator import Creator
from app.services import meta_webhook_service

TEST_SECRET = "unit-test-app-secret"


def _make_creator(data: dict) -> Creator:
    return Creator(
        id=data["id"],
        profile_id=data["profile_id"],
        name=data.get("name", ""),
    )


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _make_signed_request(user_id: str, secret: str = TEST_SECRET) -> str:
    payload = json.dumps({"algorithm": "HMAC-SHA256", "user_id": user_id}).encode()
    encoded_payload = _b64url(payload)
    signature = hmac.new(secret.encode(), encoded_payload.encode(), hashlib.sha256).digest()
    return f"{_b64url(signature)}.{encoded_payload}"


@pytest.fixture(autouse=True)
def _app_secret(monkeypatch):
    monkeypatch.setattr(settings, "APP_SECRET", TEST_SECRET)
    monkeypatch.setattr(settings, "INSTAGRAM_APP_SECRET", "unused-in-these-tests")


class FakeCreatorRepo:
    def __init__(self, creator=None):
        self._creator = creator
        self.anonymized_id = None
        self.anonymized_data = None
        self.portfolio_deleted_for = None
        self.cleared_connection_for = None

    async def get_by_instagram_user_id(self, instagram_user_id):
        return _make_creator(self._creator) if self._creator else None

    async def anonymize(self, creator_id, data):
        self.anonymized_id = creator_id
        self.anonymized_data = data
        return _make_creator({**data, "id": creator_id, "profile_id": self._creator["profile_id"]})

    async def delete_portfolio_by_creator_id(self, creator_id):
        self.portfolio_deleted_for = creator_id
        return []

    async def clear_instagram_connection(self, creator_id):
        self.cleared_connection_for = creator_id
        return _make_creator({"id": creator_id, "profile_id": self._creator["profile_id"]})


class FakeProfileRepo:
    def __init__(self):
        self.anonymized_profile_id = None
        self.anonymized_email = None

    async def anonymize(self, profile_id, anonymized_email):
        self.anonymized_profile_id = profile_id
        self.anonymized_email = anonymized_email
        return {"id": profile_id, "email": anonymized_email, "is_active": False}


class FakeDeletionRepo:
    def __init__(self):
        self.inserted = None

    async def insert_request(self, data):
        self.inserted = data
        return {**data, "id": "log-1"}


async def test_data_deletion_anonymizes_matching_creator():
    signed_request = _make_signed_request("17841441112302348")
    creator_repo = FakeCreatorRepo(creator={"id": "creator-1", "profile_id": "profile-1"})
    profile_repo = FakeProfileRepo()
    deletion_repo = FakeDeletionRepo()

    result = await meta_webhook_service.handle_data_deletion(
        signed_request, creator_repo=creator_repo, profile_repo=profile_repo, deletion_repo=deletion_repo
    )

    assert "confirmation_code" in result
    assert result["url"].endswith(result["confirmation_code"])

    assert creator_repo.portfolio_deleted_for == "creator-1"
    assert creator_repo.anonymized_id == "creator-1"
    assert creator_repo.anonymized_data["name"] == "Deleted Creator"
    assert creator_repo.anonymized_data["instagram_access_token"] is None

    assert profile_repo.anonymized_profile_id == "profile-1"
    assert "deleted-profile-1" in profile_repo.anonymized_email

    assert deletion_repo.inserted["instagram_user_id"] == "17841441112302348"
    assert deletion_repo.inserted["profile_id"] == "profile-1"
    assert deletion_repo.inserted["status"] == "completed"


async def test_data_deletion_no_matching_creator_still_acknowledges():
    signed_request = _make_signed_request("some-unknown-ig-id")
    creator_repo = FakeCreatorRepo(creator=None)
    profile_repo = FakeProfileRepo()
    deletion_repo = FakeDeletionRepo()

    result = await meta_webhook_service.handle_data_deletion(
        signed_request, creator_repo=creator_repo, profile_repo=profile_repo, deletion_repo=deletion_repo
    )

    assert "confirmation_code" in result
    assert creator_repo.anonymized_id is None
    assert profile_repo.anonymized_profile_id is None
    assert deletion_repo.inserted["status"] == "no_matching_account"
    assert deletion_repo.inserted["profile_id"] is None


async def test_data_deletion_falls_back_to_instagram_app_secret(monkeypatch):
    monkeypatch.setattr(settings, "APP_SECRET", "not-the-signing-secret")
    monkeypatch.setattr(settings, "INSTAGRAM_APP_SECRET", TEST_SECRET)
    signed_request = _make_signed_request("999", secret=TEST_SECRET)

    result = await meta_webhook_service.handle_data_deletion(
        signed_request,
        creator_repo=FakeCreatorRepo(creator=None),
        profile_repo=FakeProfileRepo(),
        deletion_repo=FakeDeletionRepo(),
    )

    assert "confirmation_code" in result


async def test_data_deletion_rejects_invalid_signature():
    signed_request = _make_signed_request("999", secret="totally-wrong-secret")

    with pytest.raises(HTTPException) as exc_info:
        await meta_webhook_service.handle_data_deletion(
            signed_request,
            creator_repo=FakeCreatorRepo(),
            profile_repo=FakeProfileRepo(),
            deletion_repo=FakeDeletionRepo(),
        )

    assert exc_info.value.status_code == 400


async def test_deauthorize_clears_connection_for_matching_creator():
    signed_request = _make_signed_request("17841441112302348")
    creator_repo = FakeCreatorRepo(creator={"id": "creator-1", "profile_id": "profile-1"})

    result = await meta_webhook_service.handle_deauthorize(signed_request, creator_repo=creator_repo)

    assert result == {"status": "ok"}
    assert creator_repo.cleared_connection_for == "creator-1"
    # deauthorize is not a deletion request — profile/name/portfolio untouched
    assert creator_repo.anonymized_id is None
    assert creator_repo.portfolio_deleted_for is None


async def test_deauthorize_no_matching_creator_is_a_no_op():
    signed_request = _make_signed_request("unknown-ig-id")
    creator_repo = FakeCreatorRepo(creator=None)

    result = await meta_webhook_service.handle_deauthorize(signed_request, creator_repo=creator_repo)

    assert result == {"status": "ok"}
    assert creator_repo.cleared_connection_for is None


async def test_deauthorize_rejects_invalid_signature():
    signed_request = _make_signed_request("999", secret="totally-wrong-secret")

    with pytest.raises(HTTPException) as exc_info:
        await meta_webhook_service.handle_deauthorize(signed_request, creator_repo=FakeCreatorRepo())

    assert exc_info.value.status_code == 400
