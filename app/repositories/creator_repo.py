from app.repositories.base import BaseRepository


class CreatorRepository(BaseRepository):
    async def get_by_id(self, creator_id: str) -> dict | None:
        return await self.select_one(
            "creators",
            columns="*",
            filters={"id": creator_id},
        )

    async def get_by_profile_id(self, profile_id: str) -> dict | None:
        return await self.select_one(
            "creators",
            columns="*",
            filters={"profile_id": profile_id},
        )

    async def get_id_by_profile_id(self, profile_id: str) -> str | None:
        row = await self.select_one(
            "creators",
            columns="id",
            filters={"profile_id": profile_id},
        )
        return row["id"] if row else None

    async def list_filtered(
        self,
        search: str | None = None,
        niche: str | None = None,
        city: str | None = None,
        follower_min: int | None = None,
        follower_max: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        query = (await self._table("creators")).select("*", count="exact")

        if search:
            query = query.ilike("name", f"%{search}%")
        if niche:
            query = query.eq("niche", niche)
        if city:
            query = query.ilike("city", f"%{city}%")
        if follower_min is not None:
            query = query.gte("follower_count", follower_min)
        if follower_max is not None:
            query = query.lte("follower_count", follower_max)

        start = (page - 1) * page_size
        end = start + page_size - 1
        result = await self._execute(query.range(start, end))

        return result.data or [], result.count or 0

    async def insert_creator(self, data: dict) -> dict | None:
        rows = await self.insert("creators", data)
        return rows[0] if rows else None

    async def update_by_profile_id(self, profile_id: str, data: dict) -> dict | None:
        rows = await self.update("creators", data, {"profile_id": profile_id})
        return rows[0] if rows else None

    async def get_niche_by_profile_id(self, profile_id: str) -> str | None:
        row = await self.select_one(
            "creators",
            columns="niche",
            filters={"profile_id": profile_id},
        )
        return row.get("niche") if row else None

    async def list_portfolio(
        self,
        creator_id: str,
        media_type: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        query = (
            (await self._table("portfolio_items"))
            .select("*", count="exact")
            .eq("creator_id", creator_id)
        )

        if media_type:
            query = query.eq("media_type", media_type)

        start = (page - 1) * page_size
        end = start + page_size - 1
        result = await self._execute(query.range(start, end))

        return result.data or [], result.count or 0

    async def count_active_collaborations(self, creator_id: str) -> int:
        return await self.count(
            "collaborations",
            filters={"creator_id": creator_id, "status": "active"},
        )

    async def list_saved_campaigns(
        self,
        creator_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        query = (
            (await self._table("saved_campaigns"))
            .select("*, campaigns!saved_campaigns_campaign_id_fkey(*)", count="exact")
            .eq("creator_id", creator_id)
        )

        start = (page - 1) * page_size
        end = start + page_size - 1
        result = await self._execute(query.range(start, end))

        return result.data or [], result.count or 0
