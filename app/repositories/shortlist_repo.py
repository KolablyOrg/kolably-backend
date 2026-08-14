from typing import Any

from app.repositories.base import BaseRepository


class ShortlistRepository(BaseRepository):
    async def list_by_business(self, business_id: str) -> list[dict[str, Any]]:
        query = (
            (await self._table("business_shortlists"))
            .select(
                "*, creator:creators!business_shortlists_creator_id_fkey("
                "id, name, username, city, niche, follower_count, engagement_rate, "
                "profile_photo_url, instagram_handle, instagram_connected, identity_status"
                ")"
            )
            .eq("business_id", business_id)
            .order("updated_at", desc=True)
        )
        result = await self._execute(query)
        return result.data or []

    async def get_by_creator(self, business_id: str, creator_id: str) -> dict[str, Any] | None:
        return await self.select_one(
            "business_shortlists",
            filters={"business_id": business_id, "creator_id": creator_id},
        )

    async def upsert(self, data: dict[str, Any]) -> dict[str, Any] | None:
        query = (
            (await self._table("business_shortlists"))
            .upsert(data, on_conflict="business_id,creator_id")
        )
        result = await self._execute(query)
        return result.data[0] if result.data else None

    async def update_for_creator(
        self, business_id: str, creator_id: str, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        rows = await self.update(
            "business_shortlists", data, {"business_id": business_id, "creator_id": creator_id}
        )
        return rows[0] if rows else None

    async def delete_for_creator(self, business_id: str, creator_id: str) -> None:
        await self.delete(
            "business_shortlists", {"business_id": business_id, "creator_id": creator_id}
        )
