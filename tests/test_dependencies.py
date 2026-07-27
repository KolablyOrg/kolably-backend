"""
Unit tests for require_instagram_connected — the mandatory onboarding gate
for creators who signed up without Instagram data (Google/email).
"""

import pytest
from fastapi import HTTPException

from app.core import dependencies
from app.core.enums import UserRole
from app.schemas.user import UserInToken


class FakeCreatorRepo:
    def __init__(self, creator=None):
        self._creator = creator

    async def get_by_profile_id(self, profile_id):
        return self._creator


def _user(role: UserRole) -> UserInToken:
    return UserInToken(id="profile-1", auth_id="auth-1", email="a@b.com", role=role, is_active=True)


def _patch_creator_repo(monkeypatch, creator):
    monkeypatch.setattr(dependencies, "CreatorRepository", lambda: FakeCreatorRepo(creator))


async def test_creator_without_instagram_is_blocked(monkeypatch):
    _patch_creator_repo(monkeypatch, {"instagram_access_token": None})

    with pytest.raises(HTTPException) as exc_info:
        await dependencies.require_instagram_connected(user=_user(UserRole.CREATOR))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "instagram_not_connected"


async def test_creator_with_no_creator_row_is_blocked(monkeypatch):
    _patch_creator_repo(monkeypatch, None)

    with pytest.raises(HTTPException) as exc_info:
        await dependencies.require_instagram_connected(user=_user(UserRole.CREATOR))

    assert exc_info.value.status_code == 403


async def test_creator_with_instagram_connected_passes(monkeypatch):
    _patch_creator_repo(monkeypatch, {"instagram_access_token": "encrypted-token"})

    result = await dependencies.require_instagram_connected(user=_user(UserRole.CREATOR))

    assert result.role == UserRole.CREATOR


async def test_superadmin_bypasses_regardless_of_instagram_state(monkeypatch):
    _patch_creator_repo(monkeypatch, None)

    result = await dependencies.require_instagram_connected(user=_user(UserRole.SUPERADMIN))

    assert result.role == UserRole.SUPERADMIN


async def test_business_bypasses_regardless_of_instagram_state(monkeypatch):
    _patch_creator_repo(monkeypatch, None)

    result = await dependencies.require_instagram_connected(user=_user(UserRole.BUSINESS))

    assert result.role == UserRole.BUSINESS
