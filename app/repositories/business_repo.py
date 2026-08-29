from app.models.business import Business
from app.models.campaign import Campaign
from app.repositories.base import BaseRepository


class BusinessRepository(BaseRepository):
    async def get_by_id(self, business_id: str) -> Business | None:
        row = await self.select_one(
            "businesses",
            columns="*",
            filters={"id": business_id},
        )
        return Business.from_row(row) if row else None

    async def get_by_profile_id(self, profile_id: str) -> Business | None:
        row = await self.select_one(
            "businesses",
            columns="*",
            filters={"profile_id": profile_id},
        )
        return Business.from_row(row) if row else None

    async def get_id_by_profile_id(self, profile_id: str) -> str | None:
        row = await self.select_one(
            "businesses",
            columns="id",
            filters={"profile_id": profile_id},
        )
        return row["id"] if row else None

    async def get_by_ids(self, business_ids: list[str]) -> list[Business]:
        if not business_ids:
            return []
        rows = await self.select(
            "businesses",
            columns="*",
            filters={"id": business_ids},
        )
        return [Business.from_row(row) for row in rows]

    async def list_filtered(
        self,
        search: str | None = None,
        category: str | None = None,
        city: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Business], int]:
        query = (await self._table("businesses")).select("*", count="exact")

        if search:
            query = query.ilike("business_name", f"%{search}%")
        if category:
            query = query.eq("category", category)
        if city:
            query = query.ilike("city", f"%{city}%")

        start = (page - 1) * page_size
        end = start + page_size - 1
        result = await self._execute(query.range(start, end))

        rows = result.data or []
        return [Business.from_row(row) for row in rows], result.count or 0

    async def insert_business(self, data: dict) -> Business | None:
        rows = await self.insert("businesses", data)
        return Business.from_row(rows[0]) if rows else None

    async def update_by_profile_id(self, profile_id: str, data: dict) -> Business | None:
        rows = await self.update("businesses", data, {"profile_id": profile_id})
        return Business.from_row(rows[0]) if rows else None

    async def update_business(self, business_id: str, data: dict) -> Business | None:
        rows = await self.update("businesses", data, {"id": business_id})
        return Business.from_row(rows[0]) if rows else None

    async def count_distinct_creators(self, business_id: str) -> int:
        """Distinct creators this business has actually collaborated with —
        excludes cancelled collaborations (a called-off invite was never worked)."""
        rows = await self.select(
            "collaborations",
            columns="creator_id",
            filters={
                "business_id": business_id,
                "status": ["active", "content_submitted", "completed"],
            },
        )
        return len({row["creator_id"] for row in rows})

    async def list_campaigns(
        self,
        business_id: str,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Campaign], int]:
        query = (await self._table("campaigns")).select("*", count="exact").eq("business_id", business_id)

        if status:
            query = query.eq("status", status)

        start = (page - 1) * page_size
        end = start + page_size - 1
        result = await self._execute(query.order("created_at", desc=True).range(start, end))

        rows = result.data or []
        return [Campaign.from_row(row) for row in rows], result.count or 0

    async def get_campaign_ids(self, business_id: str) -> list[str]:
        rows = await self.select(
            "campaigns",
            columns="id",
            filters={"business_id": business_id},
        )
        return [r["id"] for r in rows]

    async def get_collab_ids_for_campaigns(self, campaign_ids: list[str]) -> list[str]:
        rows = await self.select(
            "collaborations",
            columns="id",
            filters={"campaign_id": campaign_ids},
        )
        return [r["id"] for r in rows]

    async def get_submissions_for_collabs(self, collab_ids: list[str]) -> list[dict]:
        return await self.select(
            "content_submissions",
            columns="views,likes,comments",
            filters={"collaboration_id": collab_ids},
        )
