"""
Repository for email delivery records.
"""

from typing import Any

from app.models.email_delivery import EmailDelivery
from app.repositories.base import BaseRepository


class EmailDeliveryRepository(BaseRepository):
    async def get_by_idempotency_key(self, idempotency_key: str) -> EmailDelivery | None:
        row = await self.select_one("email_deliveries", filters={"idempotency_key": idempotency_key})
        return EmailDelivery.from_row(row) if row else None

    async def get_by_resend_id(self, resend_id: str) -> EmailDelivery | None:
        row = await self.select_one("email_deliveries", filters={"resend_id": resend_id})
        return EmailDelivery.from_row(row) if row else None

    async def insert_delivery(self, data: dict[str, Any]) -> EmailDelivery | None:
        rows = await self.insert("email_deliveries", data)
        return EmailDelivery.from_row(rows[0]) if rows else None

    async def update_delivery(self, delivery_id: str, data: dict[str, Any]) -> EmailDelivery | None:
        rows = await self.update("email_deliveries", data, filters={"id": delivery_id})
        return EmailDelivery.from_row(rows[0]) if rows else None

    async def list_by_recipient(
        self, recipient_email: str, page: int = 1, page_size: int = 20
    ) -> tuple[list[EmailDelivery], int]:
        query = (
            (await self._table("email_deliveries"))
            .select("*", count="exact")
            .eq("recipient_email", recipient_email)
            .order("created_at", desc=True)
        )
        start = (page - 1) * page_size
        end = start + page_size - 1
        result = await self._execute(query.range(start, end))
        rows = result.data or []
        return [EmailDelivery.from_row(r) for r in rows], result.count or 0
