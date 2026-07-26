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

    async def update_role(self, profile_id: str, role: str) -> dict | None:
        rows = await self.update("profiles", {"role": role}, {"id": profile_id})
        return rows[0] if rows else None
