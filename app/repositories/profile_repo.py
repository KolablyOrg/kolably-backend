from app.models.user import UserProfile
from app.repositories.base import BaseRepository


class ProfileRepository(BaseRepository):
    async def update_last_seen_at(self, profile_id: str, last_seen_at) -> UserProfile | None:
        """Persist the server-generated heartbeat timestamp for a profile."""
        return await self.update(profile_id, {"last_seen_at": last_seen_at})

    async def get_by_auth_id(self, auth_id: str) -> UserProfile | None:
        row = await self.select_one(
            "profiles",
            columns="*",
            filters={"auth_id": auth_id},
        )
        return UserProfile.from_row(row) if row else None

    async def get_by_id(self, profile_id: str) -> UserProfile | None:
        row = await self.select_one(
            "profiles",
            columns="*",
            filters={"id": profile_id},
        )
        return UserProfile.from_row(row) if row else None

    async def get_by_email(self, email: str) -> UserProfile | None:
        row = await self.select_one(
            "profiles",
            columns="*",
            filters={"email": email},
        )
        return UserProfile.from_row(row) if row else None

    async def update_role(self, profile_id: str, role: str) -> UserProfile | None:
        rows = await self.update("profiles", {"role": role}, {"id": profile_id})
        return UserProfile.from_row(rows[0]) if rows else None

    async def update(self, profile_id: str, data: dict) -> UserProfile | None:  # type: ignore[override]
        """2-arg convenience override — shadows BaseRepository.update's
        generic (table, data, filters) signature, matching every call site
        in this codebase (they all pass profile_id + a partial-update dict).
        """
        rows = await BaseRepository.update(self, "profiles", data, {"id": profile_id})
        return UserProfile.from_row(rows[0]) if rows else None

    async def anonymize(self, profile_id: str, anonymized_email: str) -> UserProfile | None:
        """Scrub the account's contact info and deactivate it — used for
        Meta's Data Deletion Callback. Keeps the row (not a hard delete of
        the auth.users record) to avoid FK/cascade uncertainty."""
        rows = await self.update(
            "profiles", {"email": anonymized_email, "is_active": False}, {"id": profile_id}
        )
        return UserProfile.from_row(rows[0]) if rows else None

    async def list_deactivated_before(self, cutoff) -> list[UserProfile]:
        """Deactivated accounts whose reactivation window (see
        auth_service._reactivate_or_reject) has closed — candidates for the
        daily cleanup job. `.lt()` isn't one of BaseRepository's generic
        eq/in_ filters, so built directly here per its own documented
        pattern for anything more complex.

        Excludes rows already anonymized (email already carries the
        deleted-account marker) so a job that runs daily doesn't keep
        re-processing the same already-scrubbed rows forever.
        """
        query = (
            (await self._table("profiles"))
            .select("*")
            .eq("is_active", False)
            .lt("deactivated_at", cutoff.isoformat())
            .not_.like("email", "deleted-%@deleted.kolably.com")
        )
        result = await self._execute(query)
        return [UserProfile.from_row(row) for row in (result.data or [])]
