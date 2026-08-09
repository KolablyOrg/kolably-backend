from app.models.invoice import Invoice
from app.repositories.base import BaseRepository


class InvoiceRepository(BaseRepository):
    async def get_by_id(self, invoice_id: str) -> Invoice | None:
        row = await self.select_one(
            "invoices",
            columns="*",
            filters={"id": invoice_id},
        )
        return Invoice.from_row(row) if row else None

    async def get_by_collaboration_id(self, collaboration_id: str) -> Invoice | None:
        row = await self.select_one(
            "invoices",
            columns="*",
            filters={"collaboration_id": collaboration_id},
        )
        return Invoice.from_row(row) if row else None

    async def list_by_creator(
        self,
        creator_id: str,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Invoice], int]:
        query = (await self._table("invoices")).select("*", count="exact").eq("creator_id", creator_id)
        if status:
            query = query.eq("status", status)
        start = (page - 1) * page_size
        end = start + page_size - 1
        result = await self._execute(query.order("created_at", desc=True).range(start, end))
        rows = result.data or []
        return [Invoice.from_row(row) for row in rows], result.count or 0

    async def list_by_business(
        self,
        business_id: str,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Invoice], int]:
        query = (await self._table("invoices")).select("*", count="exact").eq("business_id", business_id)
        if status:
            query = query.eq("status", status)
        start = (page - 1) * page_size
        end = start + page_size - 1
        result = await self._execute(query.order("created_at", desc=True).range(start, end))
        rows = result.data or []
        return [Invoice.from_row(row) for row in rows], result.count or 0

    async def list_by_collaboration_ids(self, collaboration_ids: list[str]) -> list[Invoice]:
        if not collaboration_ids:
            return []
        rows = await self.select(
            "invoices",
            columns="*",
            filters={"collaboration_id": collaboration_ids},
        )
        return [Invoice.from_row(row) for row in rows]

    async def insert_invoice(self, data: dict) -> Invoice | None:
        rows = await self.insert("invoices", data)
        return Invoice.from_row(rows[0]) if rows else None

    async def update_status(self, invoice_id: str, data: dict) -> Invoice | None:
        rows = await self.update("invoices", data, {"id": invoice_id})
        return Invoice.from_row(rows[0]) if rows else None
