"""
Shared business-identity resolution — the single place "which business does
this profile act for, and with what role" gets decided.

Before team accounts, every service resolved "my business" via
`business_repo.get_id_by_profile_id(profile_id)` (businesses.profile_id is
the sole owner). Team accounts add a second path — an active
`business_members` row — without changing what any of those call sites look
like: `get_business_id_for_profile` still returns a single business_id (or
None), just resolved via owner-or-member. `require_write_access` is the one
new thing call sites opt into, and only where a viewer should be blocked.
"""

from fastapi import HTTPException, status

from app.models.business import Business
from app.repositories.business_member_repo import BusinessMemberRepository
from app.repositories.business_repo import BusinessRepository

WRITE_ROLES = {"owner", "editor"}


async def get_business_for_profile(
    profile_id: str,
    *,
    business_repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> Business | None:
    """Like `get_business_id_for_profile`, but returns the full Business row —
    for read paths (e.g. the creator-activity banner) that need more than the id."""
    business_repo = business_repo or BusinessRepository()
    business = await business_repo.get_by_profile_id(profile_id)
    if business:
        return business

    member_repo = member_repo or BusinessMemberRepository()
    member = await member_repo.get_active_by_profile_id(profile_id)
    if not member:
        return None
    return await business_repo.get_by_id(member.business_id)


async def get_business_id_for_profile(
    profile_id: str,
    *,
    business_repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> str | None:
    """The business a profile belongs to — as the original owner, or as an
    active team member. None if neither (caller decides whether that's a 404)."""
    business_repo = business_repo or BusinessRepository()
    business_id = await business_repo.get_id_by_profile_id(profile_id)
    if business_id:
        return business_id

    member_repo = member_repo or BusinessMemberRepository()
    member = await member_repo.get_active_by_profile_id(profile_id)
    return member.business_id if member else None


async def get_role_for_profile(
    business_id: str,
    profile_id: str,
    *,
    business_repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> str | None:
    """'owner' | 'editor' | 'viewer' — None if this profile has no access to this business."""
    business_repo = business_repo or BusinessRepository()
    business = await business_repo.get_by_id(business_id)
    if business and business.profile_id == profile_id:
        return "owner"

    member_repo = member_repo or BusinessMemberRepository()
    member = await member_repo.get_active_membership(business_id, profile_id)
    return member.role if member else None


async def require_write_access(
    business_id: str,
    profile_id: str,
    *,
    business_repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> None:
    """Raise 403 if this profile can only view this business (viewer role)."""
    role = await get_role_for_profile(business_id, profile_id, business_repo=business_repo, member_repo=member_repo)
    if role not in WRITE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers can't make changes — ask an owner or editor on this account.",
        )
