from app.repositories.base import BaseRepository


class DataDeletionRepository(BaseRepository):
    async def get_by_confirmation_code(self, confirmation_code: str) -> dict | None:
        return await self.select_one(
            "data_deletion_requests",
            columns="*",
            filters={"confirmation_code": confirmation_code},
        )

    async def insert_request(self, data: dict) -> dict | None:
        rows = await self.insert("data_deletion_requests", data)
        return rows[0] if rows else None
