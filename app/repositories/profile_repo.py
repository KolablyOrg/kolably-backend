from app.repositories.base import BaseRepository


class ProfileRepository(BaseRepository):
    async def get_by_auth_id(self, auth_id: str) -> dict | None:
        return await self.select_one(
            "profiles",
            columns="*",
            filters={"auth_id": auth_id},
        )

    async def get_by_id(self, profile_id: str) -> dict | None:
        return await self.select_one(
            "profiles",
            columns="*",
            filters={"id": profile_id},
        )
