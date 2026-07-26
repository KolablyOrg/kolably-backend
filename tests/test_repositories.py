"""
Unit tests for BaseRepository — no real Supabase involved.

The fake client/builder record the call chain so we can assert on *how*
queries are built (not just what they return).
"""

import pytest
from postgrest.exceptions import APIError

from app.core.exceptions import DatabaseError
from app.repositories.base import BaseRepository

_SENTINEL = object()


class FakeResponse:
    def __init__(self, data=None, count=None):
        self.data = data
        self.count = count


class FakeQuery:
    """Duck-typed postgrest builder: records calls, returns canned response."""

    def __init__(self, response=_SENTINEL, exc: Exception | None = None):
        self.response = FakeResponse(data=[]) if response is _SENTINEL else response
        self.exc = exc
        self.calls: list[str] = []

    def _record(self, name: str) -> "FakeQuery":
        self.calls.append(name)
        return self

    def select(self, *args, **kwargs) -> "FakeQuery":
        return self._record("select")

    def insert(self, *args, **kwargs) -> "FakeQuery":
        return self._record("insert")

    def update(self, *args, **kwargs) -> "FakeQuery":
        return self._record("update")

    def delete(self, *args, **kwargs) -> "FakeQuery":
        return self._record("delete")

    def upsert(self, *args, **kwargs) -> "FakeQuery":
        return self._record("upsert")

    def eq(self, *args, **kwargs) -> "FakeQuery":
        return self._record("eq")

    def in_(self, *args, **kwargs) -> "FakeQuery":
        return self._record("in_")

    def order(self, *args, **kwargs) -> "FakeQuery":
        return self._record("order")

    def maybe_single(self, *args, **kwargs) -> "FakeQuery":
        return self._record("maybe_single")

    async def execute(self):
        if self.exc:
            raise self.exc
        return self.response


class FakeClient:
    def __init__(self, query: FakeQuery):
        self._query = query

    def table(self, name: str) -> FakeQuery:
        return self._query


def _repo(query: FakeQuery) -> BaseRepository:
    return BaseRepository(client=FakeClient(query))


async def test_delete_applies_filters_after_delete_call():
    """Regression: filters must be applied to the delete builder, not the raw
    table builder (which has no `.eq` and would raise AttributeError)."""
    query = FakeQuery(FakeResponse(data=[{"id": "1"}]))
    repo = _repo(query)

    rows = await repo.delete("campaigns", {"id": "1"})

    assert rows == [{"id": "1"}]
    assert query.calls == ["delete", "eq"]


async def test_select_one_returns_none_when_no_row():
    """maybe_single() returns None (not a response) on 0 rows — must not crash."""
    query = FakeQuery(response=None)
    repo = _repo(query)

    result = await repo.select_one("creators", filters={"id": "missing"})

    assert result is None
    assert query.calls == ["select", "eq", "maybe_single"]


async def test_select_one_returns_row():
    row = {"id": "c1", "name": "Alice"}
    query = FakeQuery(FakeResponse(data=row))
    repo = _repo(query)

    assert await repo.select_one("creators", filters={"id": "c1"}) == row


async def test_select_uses_in_for_list_filters():
    query = FakeQuery(FakeResponse(data=[{"id": "1"}]))
    repo = _repo(query)

    rows = await repo.select("campaigns", filters={"id": ["1", "2"], "status": "active"})

    assert rows == [{"id": "1"}]
    assert query.calls == ["select", "in_", "eq"]


async def test_count_returns_exact_count():
    query = FakeQuery(FakeResponse(data=[], count=7))
    repo = _repo(query)

    assert await repo.count("collaborations", filters={"status": "active"}) == 7


async def test_api_error_is_translated_to_database_error():
    """Raw postgrest APIError must become a consistent HTTP 500, not a stack trace."""
    api_error = APIError({"message": "relation does not exist", "code": "42P01", "hint": None, "details": None})
    query = FakeQuery(exc=api_error)
    repo = _repo(query)

    with pytest.raises(DatabaseError) as exc_info:
        await repo.select("creators")

    assert exc_info.value.status_code == 500
    assert exc_info.value.__cause__ is api_error


async def test_update_and_insert_roundtrip_data():
    rows = [{"id": "c1", "name": "Alice"}]
    query = FakeQuery(FakeResponse(data=rows))
    repo = _repo(query)

    assert await repo.insert("creators", {"name": "Alice"}) == rows
    assert await repo.update("creators", {"name": "Bob"}, {"id": "c1"}) == rows
    assert query.calls == ["insert", "update", "eq"]
