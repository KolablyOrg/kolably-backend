from app.models.business_member import BusinessMember
from app.repositories.base import BaseRepository


class BusinessMemberRepository(BaseRepository):
    async def get_active_by_profile_id(self, profile_id: str) -> BusinessMember | None:
        """The active membership a profile belongs to — a profile can only
        actively belong to one business (see the migration's unique index)."""
        row = await self.select_one(
            "business_members",
            columns="*",
            filters={"profile_id": profile_id, "status": "active"},
        )
        return BusinessMember.from_row(row) if row else None

    async def get_active_membership(self, business_id: str, profile_id: str) -> BusinessMember | None:
        row = await self.select_one(
            "business_members",
            columns="*",
            filters={"business_id": business_id, "profile_id": profile_id, "status": "active"},
        )
        return BusinessMember.from_row(row) if row else None

    async def get_pending_by_email(self, business_id: str, email: str) -> BusinessMember | None:
        row = await self.select_one(
            "business_members",
            columns="*",
            filters={"business_id": business_id, "invited_email": email, "status": "pending"},
        )
        return BusinessMember.from_row(row) if row else None

    async def get_any_pending_by_email(self, email: str) -> BusinessMember | None:
        """Used by accept-invite (POST /businesses/join) — the caller only
        knows their own email, not which business invited them."""
        row = await self.select_one(
            "business_members",
            columns="*",
            filters={"invited_email": email, "status": "pending"},
        )
        return BusinessMember.from_row(row) if row else None

    async def list_by_business(self, business_id: str) -> list[BusinessMember]:
        rows = await self.select(
            "business_members",
            columns="*",
            filters={"business_id": business_id},
            order_by="created_at",
        )
        return [BusinessMember.from_row(row) for row in rows if row.get("status") != "revoked"]

    async def get_by_id(self, member_id: str) -> BusinessMember | None:
        row = await self.select_one("business_members", columns="*", filters={"id": member_id})
        return BusinessMember.from_row(row) if row else None

    async def insert_member(self, data: dict) -> BusinessMember | None:
        rows = await self.insert("business_members", data)
        return BusinessMember.from_row(rows[0]) if rows else None

    async def update_member(self, member_id: str, data: dict) -> BusinessMember | None:
        rows = await self.update("business_members", data, {"id": member_id})
        return BusinessMember.from_row(rows[0]) if rows else None

    async def delete_member(self, member_id: str) -> None:
        await self.delete("business_members", {"id": member_id})
