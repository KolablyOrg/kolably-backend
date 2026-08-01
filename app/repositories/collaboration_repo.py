from app.models.collaboration import Collaboration
from app.repositories.base import BaseRepository


class CollaborationRepository(BaseRepository):
    async def get_by_id(self, collaboration_id: str) -> Collaboration | None:
        row = await self.select_one(
            "collaborations",
            columns="*",
            filters={"id": collaboration_id},
        )
        return Collaboration.from_row(row) if row else None

    async def list_by_creator(
        self,
        creator_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Collaboration], int]:
        query = (
            (await self._table("collaborations"))
            .select("*", count="exact")
            .eq("creator_id", creator_id)
        )

        start = (page - 1) * page_size
        end = start + page_size - 1
        result = await self._execute(query.range(start, end))

        rows = result.data or []
        return [Collaboration.from_row(row) for row in rows], result.count or 0

    async def list_by_business(
        self,
        business_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Collaboration], int]:
        query = (
            (await self._table("collaborations"))
            .select("*", count="exact")
            .eq("business_id", business_id)
        )

        start = (page - 1) * page_size
        end = start + page_size - 1
        result = await self._execute(query.range(start, end))

        rows = result.data or []
        return [Collaboration.from_row(row) for row in rows], result.count or 0

    async def list_submissions(self, collaboration_id: str) -> list[dict]:
        return await self.select(
            "content_submissions",
            columns="*",
            filters={"collaboration_id": collaboration_id},
        )
