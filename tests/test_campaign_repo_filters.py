"""
Unit tests for CampaignRepository's discover filters — no real Supabase.

Regression cover for the deliverables filter: `deliverables` is a JSONB array
of objects, so `contains("deliverables", ["reel"])` matched nothing and the
filter silently returned an empty feed.
"""

from app.repositories.campaign_repo import CampaignRepository


class FakeResponse:
    def __init__(self, data=None, count=None):
        self.data = data
        self.count = count


class FakeQuery:
    """Duck-typed postgrest builder that records how the query was built."""

    def __init__(self, rows_by_content_type: dict[str, list[dict]]):
        self._rows_by_content_type = rows_by_content_type
        self.contains_args: list[tuple[str, list]] = []
        self._response = FakeResponse(data=[], count=0)

    def select(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def in_(self, *args, **kwargs):
        return self

    def range(self, *args, **kwargs):
        return self

    def or_(self, *args, **kwargs):
        return self

    def contains(self, column: str, value):
        self.contains_args.append((column, value))
        content_type = value[0].get("content_type") if isinstance(value[0], dict) else value[0]
        self._response = FakeResponse(data=self._rows_by_content_type.get(content_type, []))
        return self

    async def execute(self):
        return self._response


class FakeClient:
    def __init__(self, query: FakeQuery):
        self._query = query

    def table(self, name: str):
        return self._query


async def test_deliverable_ids_query_uses_object_containment():
    """A bare string list can never be contained in an array of objects —
    each content type has to be matched as `{"content_type": ...}`."""
    query = FakeQuery({"reel": [{"id": "c1"}, {"id": "c2"}]})
    repo = CampaignRepository(client=FakeClient(query))

    ids = await repo._campaign_ids_with_deliverables(["reel"])

    assert ids == ["c1", "c2"]
    assert query.contains_args == [("deliverables", [{"content_type": "reel"}])]


async def test_deliverable_ids_union_across_content_types_without_duplicates():
    """Multi-select is an OR: a campaign matching two selected types appears once."""
    query = FakeQuery(
        {
            "reel": [{"id": "c1"}, {"id": "c2"}],
            "story": [{"id": "c2"}, {"id": "c3"}],
        }
    )
    repo = CampaignRepository(client=FakeClient(query))

    ids = await repo._campaign_ids_with_deliverables(["reel", "story"])

    assert ids == ["c1", "c2", "c3"]
    assert len(query.contains_args) == 2


async def test_list_active_returns_empty_when_no_deliverable_matches():
    """No campaign has the selected deliverable → empty page, not the whole feed."""
    query = FakeQuery({})
    repo = CampaignRepository(client=FakeClient(query))

    campaigns, total = await repo.list_active(deliverables=["video"])

    assert campaigns == []
    assert total == 0
