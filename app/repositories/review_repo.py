from typing import Any

from app.repositories.base import BaseRepository


class ReviewRepository(BaseRepository):
    """Post-collaboration reviews (`collaboration_reviews`)."""

    TABLE = "collaboration_reviews"

    async def get_by_collaboration_and_reviewer(
        self,
        collaboration_id: str,
        reviewer_profile_id: str,
    ) -> dict | None:
        """The reviewer's own review for this collaboration, if any.

        Drives both the "already reviewed" check and the upsert path — the
        table allows one review per reviewer per collaboration, so a second
        submission is an edit rather than a new row.
        """
        return await self.select_one(
            self.TABLE,
            filters={
                "collaboration_id": collaboration_id,
                "reviewer_profile_id": reviewer_profile_id,
            },
        )

    async def insert_review(self, data: dict[str, Any]) -> dict | None:
        rows = await self.insert(self.TABLE, data)
        return rows[0] if rows else None

    async def update_review(self, review_id: str, data: dict[str, Any]) -> dict | None:
        rows = await self.update(self.TABLE, data, {"id": review_id})
        return rows[0] if rows else None

    async def list_for_reviewee(
        self,
        reviewee_profile_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        query = (
            (await self._table(self.TABLE))
            .select("*", count="exact")
            .eq("reviewee_profile_id", reviewee_profile_id)
            .order("created_at", desc=True)
        )
        start = (page - 1) * page_size
        result = await self._execute(query.range(start, start + page_size - 1))
        return (result.data or []), (result.count or 0)

    async def rating_summary(self, reviewee_profile_id: str) -> dict:
        """Average + count for a profile.

        Averaged in Python rather than SQL: PostgREST has no aggregate
        endpoint here, and review volumes per profile are small enough that
        fetching the ratings is cheaper than adding a view or RPC for it.
        """
        result = await self._execute(
            (await self._table(self.TABLE))
            .select("rating")
            .eq("reviewee_profile_id", reviewee_profile_id)
        )
        ratings = [r["rating"] for r in (result.data or []) if r.get("rating") is not None]
        if not ratings:
            return {"average_rating": None, "review_count": 0}
        return {
            "average_rating": round(sum(ratings) / len(ratings), 2),
            "review_count": len(ratings),
        }
