from app.repositories.base import BaseRepository


class NotificationRepository(BaseRepository):
    async def list_by_profile(
        self,
        profile_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        query = (
            (await self._table("notifications"))
            .select("*", count="exact")
            .eq("profile_id", profile_id)
        )

        start = (page - 1) * page_size
        end = start + page_size - 1
        result = await self._execute(query.range(start, end))

        return result.data or [], result.count or 0

    async def count_unread(self, profile_id: str) -> int:
        query = (
            (await self._table("notifications"))
            .select("id", count="exact")
            .eq("profile_id", profile_id)
            .eq("is_read", False)
        )
        result = await self._execute(query)
        return result.count or 0
