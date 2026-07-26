from app.repositories.base import BaseRepository


class CollaborationRepository(BaseRepository):
    async def get_by_id(self, collaboration_id: str) -> dict | None:
        return await self.select_one(
            "collaborations",
            columns="*",
            filters={"id": collaboration_id},
        )

    async def list_by_creator(
        self,
        creator_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        query = (
            self._table("collaborations")
            .select("*", count="exact")
            .eq("creator_id", creator_id)
        )

        start = (page - 1) * page_size
        end = start + page_size - 1
        result = query.range(start, end).execute()

        return result.data or [], result.count or 0

    async def list_by_business(
        self,
        business_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        query = (
            self._table("collaborations")
            .select("*", count="exact")
            .eq("business_id", business_id)
        )

        start = (page - 1) * page_size
        end = start + page_size - 1
        result = query.range(start, end).execute()

        return result.data or [], result.count or 0

    async def list_submissions(self, collaboration_id: str) -> list[dict]:
        return await self.select(
            "content_submissions",
            columns="*",
            filters={"collaboration_id": collaboration_id},
        )
