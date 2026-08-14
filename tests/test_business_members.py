"""
Unit tests for business team accounts — business_access resolver +
business_service team functions, repositories injected as fakes.
"""

import pytest
from fastapi import HTTPException

from app.core.enums import UserRole
from app.models.business import Business
from app.models.business_member import BusinessMember
from app.schemas.business import TeamInviteRequest, TeamRoleUpdateRequest
from app.services import business_access, business_service

BUSINESS_ROW = {
    "id": "b1",
    "profile_id": "owner-1",
    "business_name": "Cafe Kolab",
    "owner_name": "Bob",
    "category": "food",
    "city": "Springfield",
    "created_at": "2024-01-01T00:00:00+00:00",
}


class FakeBusinessRepo:
    def __init__(self, row=None):
        self._row = row

    async def get_by_id(self, business_id: str):
        return Business.from_row(self._row) if self._row else None

    async def get_by_profile_id(self, profile_id: str):
        if self._row and self._row["profile_id"] == profile_id:
            return Business.from_row(self._row)
        return None

    async def get_id_by_profile_id(self, profile_id: str):
        if self._row and self._row["profile_id"] == profile_id:
            return self._row["id"]
        return None


class FakeMemberRepo:
    def __init__(self, members=None):
        self._members = list(members or [])
        self.inserted: list[dict] = []
        self.updated: list[tuple[str, dict]] = []

    async def get_active_by_profile_id(self, profile_id):
        for m in self._members:
            if m.profile_id == profile_id and m.status == "active":
                return m
        return None

    async def get_active_membership(self, business_id, profile_id):
        for m in self._members:
            if m.business_id == business_id and m.profile_id == profile_id and m.status == "active":
                return m
        return None

    async def get_pending_by_email(self, business_id, email):
        for m in self._members:
            if m.business_id == business_id and m.invited_email == email and m.status == "pending":
                return m
        return None

    async def get_any_pending_by_email(self, email):
        for m in self._members:
            if m.invited_email == email and m.status == "pending":
                return m
        return None

    async def get_by_id(self, member_id):
        return next((m for m in self._members if m.id == member_id), None)

    async def list_by_business(self, business_id):
        return [m for m in self._members if m.business_id == business_id and m.status != "revoked"]

    async def insert_member(self, data):
        member = BusinessMember(
            id=f"m{len(self._members) + 1}",
            business_id=data["business_id"],
            role=data["role"],
            invited_email=data["invited_email"],
            status=data.get("status", "pending"),
            invited_by=data.get("invited_by"),
            created_at="2024-01-01T00:00:00+00:00",
        )
        self._members.append(member)
        self.inserted.append(data)
        return member

    async def update_member(self, member_id, data):
        for i, m in enumerate(self._members):
            if m.id == member_id:
                for k, v in data.items():
                    setattr(m, k, v)
                self.updated.append((member_id, data))
                return m
        return None


def _member(business_id="b1", profile_id=None, role="viewer", status="active", email="teammate@example.com"):
    return BusinessMember(
        id="m1", business_id=business_id, profile_id=profile_id, role=role,
        status=status, invited_email=email, created_at="2024-01-01T00:00:00+00:00",
    )


# ── business_access resolver ─────────────────────────────────────────

async def test_owner_resolves_via_business_repo():
    business_id = await business_access.get_business_id_for_profile(
        "owner-1", business_repo=FakeBusinessRepo(dict(BUSINESS_ROW)), member_repo=FakeMemberRepo()
    )
    assert business_id == "b1"


async def test_team_member_resolves_via_member_repo():
    members = [_member(profile_id="teammate-1", role="editor")]
    business_id = await business_access.get_business_id_for_profile(
        "teammate-1", business_repo=FakeBusinessRepo(dict(BUSINESS_ROW)), member_repo=FakeMemberRepo(members)
    )
    assert business_id == "b1"


async def test_unrelated_profile_resolves_to_none():
    business_id = await business_access.get_business_id_for_profile(
        "stranger", business_repo=FakeBusinessRepo(dict(BUSINESS_ROW)), member_repo=FakeMemberRepo()
    )
    assert business_id is None


async def test_owner_role_is_owner():
    role = await business_access.get_role_for_profile(
        "b1", "owner-1", business_repo=FakeBusinessRepo(dict(BUSINESS_ROW)), member_repo=FakeMemberRepo()
    )
    assert role == "owner"


async def test_viewer_cannot_write():
    members = [_member(profile_id="viewer-1", role="viewer")]
    with pytest.raises(HTTPException) as exc_info:
        await business_access.require_write_access(
            "b1", "viewer-1", business_repo=FakeBusinessRepo(dict(BUSINESS_ROW)), member_repo=FakeMemberRepo(members)
        )
    assert exc_info.value.status_code == 403


async def test_editor_can_write():
    members = [_member(profile_id="editor-1", role="editor")]
    # Should not raise.
    await business_access.require_write_access(
        "b1", "editor-1", business_repo=FakeBusinessRepo(dict(BUSINESS_ROW)), member_repo=FakeMemberRepo(members)
    )


# ── business_service team functions ──────────────────────────────────

async def test_list_team_members_includes_synthetic_owner_row():
    members = [_member(profile_id="editor-1", role="editor")]
    business_repo = FakeBusinessRepo(dict(BUSINESS_ROW))
    result = await business_service.list_team_members(
        "owner-1", business_repo=business_repo, member_repo=FakeMemberRepo(members)
    )
    assert result[0].role == "owner"
    assert result[0].profile_id == "owner-1"
    assert any(m.role == "editor" for m in result)


async def test_invite_team_member_owner_only():
    # An editor legitimately belongs to the business (so this exercises
    # _require_owner's role check, not _get_business_id_for_user's 404 path
    # for someone with no relationship to the business at all).
    business_repo = FakeBusinessRepo(dict(BUSINESS_ROW))
    member_repo = FakeMemberRepo([_member(profile_id="editor-1", role="editor")])

    with pytest.raises(HTTPException) as exc_info:
        await business_service.invite_team_member(
            "editor-1",
            TeamInviteRequest(email="new@example.com", role="editor"),
            business_repo=business_repo,
            member_repo=member_repo,
        )
    assert exc_info.value.status_code == 403


async def test_invite_team_member_duplicate_pending_conflict():
    business_repo = FakeBusinessRepo(dict(BUSINESS_ROW))
    member_repo = FakeMemberRepo([_member(profile_id=None, role="viewer", status="pending", email="dup@example.com")])

    with pytest.raises(HTTPException) as exc_info:
        await business_service.invite_team_member(
            "owner-1",
            TeamInviteRequest(email="dup@example.com", role="viewer"),
            business_repo=business_repo,
            member_repo=member_repo,
        )
    assert exc_info.value.status_code == 409


async def test_remove_team_member_owner_only():
    business_repo = FakeBusinessRepo(dict(BUSINESS_ROW))
    member_repo = FakeMemberRepo([_member(profile_id="editor-1", role="editor")])

    with pytest.raises(HTTPException) as exc_info:
        await business_service.remove_team_member(
            "not-the-owner", "m1", business_repo=business_repo, member_repo=member_repo
        )
    assert exc_info.value.status_code == 403

    result = await business_service.remove_team_member(
        "owner-1", "m1", business_repo=business_repo, member_repo=member_repo
    )
    assert result["message"]
    assert member_repo.updated[-1] == ("m1", {"status": "revoked"})


async def test_update_team_member_role_owner_only():
    business_repo = FakeBusinessRepo(dict(BUSINESS_ROW))
    member_repo = FakeMemberRepo([_member(profile_id="viewer-1", role="viewer")])

    updated = await business_service.update_team_member_role(
        "owner-1", "m1", TeamRoleUpdateRequest(role="editor"), business_repo=business_repo, member_repo=member_repo
    )
    assert updated.role == "editor"


async def test_join_business_links_pending_invite():
    member_repo = FakeMemberRepo(
        [_member(profile_id=None, role="editor", status="pending", email="invitee@example.com")]
    )

    result = await business_service.join_business("new-profile-id", "invitee@example.com", member_repo=member_repo)
    assert result.status == "active"
    assert result.profile_id == "new-profile-id"


async def test_join_business_404_when_no_pending_invite():
    member_repo = FakeMemberRepo()
    with pytest.raises(HTTPException) as exc_info:
        await business_service.join_business("new-profile-id", "nobody@example.com", member_repo=member_repo)
    assert exc_info.value.status_code == 404


async def test_ensure_business_access_allows_editor_write():
    business = Business.from_row(dict(BUSINESS_ROW))
    members = [_member(profile_id="editor-1", role="editor")]
    # Should not raise.
    await business_service._ensure_business_access(
        business, "editor-1", UserRole.BUSINESS, member_repo=FakeMemberRepo(members)
    )


async def test_ensure_business_access_blocks_viewer_write():
    business = Business.from_row(dict(BUSINESS_ROW))
    members = [_member(profile_id="viewer-1", role="viewer")]
    with pytest.raises(HTTPException) as exc_info:
        await business_service._ensure_business_access(
            business, "viewer-1", UserRole.BUSINESS, member_repo=FakeMemberRepo(members)
        )
    assert exc_info.value.status_code == 403
