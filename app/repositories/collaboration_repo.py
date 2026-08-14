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
        campaign_id: str | None = None,
    ) -> tuple[list[Collaboration], int]:
        query = (
            (await self._table("collaborations"))
            .select("*", count="exact")
            .eq("creator_id", creator_id)
        )
        if campaign_id:
            query = query.eq("campaign_id", campaign_id)

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
        campaign_id: str | None = None,
    ) -> tuple[list[Collaboration], int]:
        query = (
            (await self._table("collaborations"))
            .select("*", count="exact")
            .eq("business_id", business_id)
        )
        if campaign_id:
            query = query.eq("campaign_id", campaign_id)

        start = (page - 1) * page_size
        end = start + page_size - 1
        result = await self._execute(query.range(start, end))

        rows = result.data or []
        return [Collaboration.from_row(row) for row in rows], result.count or 0

    async def list_by_campaign(
        self,
        campaign_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Collaboration], int]:
        query = (
            (await self._table("collaborations"))
            .select("*", count="exact")
            .eq("campaign_id", campaign_id)
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

    async def get_latest_submission(
        self, collaboration_id: str, submission_type: str
    ) -> dict | None:
        """Most recent submission of a given type ('draft' or 'live') for a
        collaboration — a collab can accumulate multiple draft rows across
        revision rounds, so callers that care about "the current one" (e.g.
        live-post verification) need the latest, not just any."""
        query = (
            (await self._table("content_submissions"))
            .select("*")
            .eq("collaboration_id", collaboration_id)
            .eq("submission_type", submission_type)
            .order("submitted_at", desc=True)
            .limit(1)
        )
        result = await self._execute(query)
        return result.data[0] if result and result.data else None

    async def insert_submission(self, data: dict) -> dict | None:
        rows = await self.insert("content_submissions", data)
        return rows[0] if rows else None

    async def update_submission(self, submission_id: str, data: dict) -> dict | None:
        rows = await self.update("content_submissions", data, {"id": submission_id})
        return rows[0] if rows else None

    async def insert_collaboration(self, data: dict) -> Collaboration | None:
        rows = await self.insert("collaborations", data)
        return Collaboration.from_row(rows[0]) if rows else None

    async def update_status(
        self, collaboration_id: str, data: dict
    ) -> Collaboration | None:
        rows = await self.update("collaborations", data, {"id": collaboration_id})
        return Collaboration.from_row(rows[0]) if rows else None

    async def list_revision_history(self, collaboration_id: str) -> list[dict]:
        return await self.select(
            "collaboration_revision_history",
            columns="*",
            filters={"collaboration_id": collaboration_id},
            order_by="created_at",
            order_desc=True,
        )

    async def insert_revision_history(self, data: dict) -> dict | None:
        rows = await self.insert("collaboration_revision_history", data)
        return rows[0] if rows else None
