"""
Base repository — the only layer that talks to Supabase.

Deliberate split of responsibilities:
- This base class covers only the truly generic operations: single-row
  lookups, inserts, updates, deletes, counts, and simple `eq`/`in_` filters.
- Anything more complex (joins, `ilike`, `gte`/`lte`, ordering + pagination
  via `.range()`) is built directly in the per-repository method with
  `await self._table(...)`, and executed through `self._execute(query)` so
  error translation always applies.

Notes:
- The default client is the service-role admin client, which BYPASSES RLS —
  every ownership/role check must happen in the service layer (see
  `app/core/supabase.py`).
- All queries go through `_execute()`, which awaits the async client's
  `.execute()` (never blocks the event loop) and translates postgrest
  `APIError`s into a consistent `DatabaseError` (HTTP 500) instead of
  leaking raw stack traces.
"""

import logging
from typing import Any

from postgrest.exceptions import APIError
from supabase import AsyncClient

from app.core.exceptions import DatabaseError
from app.core.supabase import get_supabase_admin_client

logger = logging.getLogger(__name__)


class BaseRepository:
    def __init__(self, client: AsyncClient | None = None) -> None:
        # Injectable for tests; resolved lazily so repo construction stays cheap.
        self._client = client

    async def _get_client(self) -> AsyncClient:
        if self._client is None:
            self._client = await get_supabase_admin_client()
        return self._client

    async def _table(self, name: str):
        return (await self._get_client()).table(name)

    async def _execute(self, query: Any) -> Any:
        """Await a built postgrest query, translating APIError → DatabaseError.

        Passes through `None` untouched (`maybe_single()` returns None on 0 rows).
        """
        try:
            return await query.execute()
        except APIError as exc:
            logger.exception("Supabase query failed: %s", exc)
            raise DatabaseError() from exc

    async def select(
        self,
        table: str,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        order_desc: bool = False,
    ) -> list[dict]:
        query = (await self._table(table)).select(columns)

        if filters:
            for key, value in filters.items():
                if isinstance(value, list):
                    query = query.in_(key, value)
                elif value is not None:
                    query = query.eq(key, value)

        if order_by:
            query = query.order(order_by, desc=order_desc)

        result = await self._execute(query)
        return result.data or []

    async def select_one(
        self,
        table: str,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
    ) -> dict | None:
        query = (await self._table(table)).select(columns)

        if filters:
            for key, value in filters.items():
                query = query.eq(key, value)

        # maybe_single() returns None (not a response) when 0 rows match.
        result = await self._execute(query.maybe_single())
        return result.data if result else None

    async def insert(self, table: str, data: dict | list[dict]) -> list[dict]:
        result = await self._execute((await self._table(table)).insert(data))
        return result.data or []

    async def update(
        self,
        table: str,
        data: dict,
        filters: dict[str, Any],
    ) -> list[dict]:
        query = (await self._table(table)).update(data)

        for key, value in filters.items():
            query = query.eq(key, value)

        result = await self._execute(query)
        return result.data or []

    async def delete(self, table: str, filters: dict[str, Any]) -> list[dict]:
        query = (await self._table(table)).delete()

        for key, value in filters.items():
            query = query.eq(key, value)

        result = await self._execute(query)
        return result.data or []

    async def count(
        self,
        table: str,
        filters: dict[str, Any] | None = None,
    ) -> int:
        query = (await self._table(table)).select("id", count="exact")

        if filters:
            for key, value in filters.items():
                if isinstance(value, list):
                    query = query.in_(key, value)
                elif value is not None:
                    query = query.eq(key, value)

        result = await self._execute(query)
        return result.count or 0

    async def upsert(self, table: str, data: dict | list[dict]) -> list[dict]:
        result = await self._execute((await self._table(table)).upsert(data))
        return result.data or []
