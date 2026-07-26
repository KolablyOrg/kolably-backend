from typing import Any

from supabase import Client

from app.core.supabase import get_supabase_admin_client


class BaseRepository:
    def __init__(self, client: Client | None = None):
        self.client = client or get_supabase_admin_client()

    def _table(self, name: str):
        return self.client.table(name)

    async def select(
        self,
        table: str,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        order_desc: bool = False,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict]:
        query = self._table(table).select(columns)

        if filters:
            for key, value in filters.items():
                if isinstance(value, list):
                    query = query.in_(key, value)
                elif value is not None:
                    query = query.eq(key, value)

        if order_by:
            query = query.order(order_by, desc=order_desc)

        if limit is not None:
            query = query.limit(limit)
        if offset is not None:
            query = query.offset(offset)

        result = query.execute()
        return result.data or []

    async def select_one(
        self,
        table: str,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
    ) -> dict | None:
        query = self._table(table).select(columns)

        if filters:
            for key, value in filters.items():
                query = query.eq(key, value)

        result = query.maybe_single().execute()
        return result.data

    async def insert(self, table: str, data: dict | list[dict]) -> list[dict]:
        result = self._table(table).insert(data).execute()
        return result.data or []

    async def update(
        self,
        table: str,
        data: dict,
        filters: dict[str, Any],
    ) -> list[dict]:
        query = self._table(table).update(data)

        for key, value in filters.items():
            query = query.eq(key, value)

        result = query.execute()
        return result.data or []

    async def delete(self, table: str, filters: dict[str, Any]) -> list[dict]:
        query = self._table(table)

        for key, value in filters.items():
            query = query.eq(key, value)

        result = query.delete().execute()
        return result.data or []

    async def count(
        self,
        table: str,
        filters: dict[str, Any] | None = None,
    ) -> int:
        query = self._table(table).select("id", count="exact")

        if filters:
            for key, value in filters.items():
                if isinstance(value, list):
                    query = query.in_(key, value)
                elif value is not None:
                    query = query.eq(key, value)

        result = query.execute()
        return result.count or 0

    async def upsert(self, table: str, data: dict | list[dict]) -> list[dict]:
        result = self._table(table).upsert(data).execute()
        return result.data or []
