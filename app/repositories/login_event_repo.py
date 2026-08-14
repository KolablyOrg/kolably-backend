from app.repositories.base import BaseRepository


class LoginEventRepository(BaseRepository):
    async def record(self, profile_id: str, ip_address: str | None, user_agent: str | None) -> None:
        await self.insert(
            "login_events",
            {"profile_id": profile_id, "ip_address": ip_address, "user_agent": user_agent},
        )

    async def list_recent(self, profile_id: str, limit: int = 10) -> list[dict]:
        rows = await self.select(
            "login_events",
            columns="id,ip_address,user_agent,created_at",
            filters={"profile_id": profile_id},
            order_by="created_at",
            order_desc=True,
        )
        return rows[:limit]
