from app.models.campaign import Campaign
from app.repositories.base import BaseRepository


def _sanitize_search_term(term: str) -> str:
    """Strip PostgREST `or_()` grammar breakers and LIKE wildcards from user input."""
    cleaned = term.strip()
    for ch in (",", "(", ")", ".", "%", "_", "*", '"', "'", "&"):
        cleaned = cleaned.replace(ch, " ")
    return " ".join(cleaned.split())


class CampaignRepository(BaseRepository):
    async def get_by_id(self, campaign_id: str) -> Campaign | None:
        row = await self.select_one(
            "campaigns",
            columns="*",
            filters={"id": campaign_id},
        )
        return Campaign.from_row(row) if row else None

    async def _business_ids_matching_name(self, term: str) -> list[str]:
        result = await self._execute(
            (await self._table("businesses"))
            .select("id")
            .ilike("business_name", f"%{term}%")
            .limit(50)
        )
        return [row["id"] for row in (result.data or []) if row.get("id")]

    async def list_active(
        self,
        search: str | None = None,
        category: str | None = None,
        page: int = 1,
        page_size: int = 20,
        *,
        extra_category_values: list[str] | None = None,
        location: list[str] | None = None,
        compensation_type: list[str] | None = None,
        cash_amount_min: float | None = None,
        cash_amount_max: float | None = None,
        deliverables: list[str] | None = None,
        only_qualified: bool | None = None,
    ) -> tuple[list[Campaign], int]:
        query = (
            (await self._table("campaigns"))
            .select("*", count="exact")
            .eq("status", "active")
            .order("created_at", desc=True)
        )

        if search:
            term = _sanitize_search_term(search)
            if term:
                brand_ids = await self._business_ids_matching_name(term)
                clauses = [
                    f"title.ilike.%{term}%",
                    f"description.ilike.%{term}%",
                    f"location.ilike.%{term}%",
                    f"creator_category.ilike.%{term}%",
                ]
                if extra_category_values:
                    # Exact category matches from label→value mapping (e.g. "Food & Dining" → food)
                    unique_cats = list(dict.fromkeys(extra_category_values))
                    if unique_cats:
                        clauses.append(f"creator_category.in.({','.join(unique_cats)})")
                if brand_ids:
                    clauses.append(f"business_id.in.({','.join(brand_ids)})")
                query = query.or_(",".join(clauses))

        if category:
            query = query.eq("creator_category", category)

        if location:
            query = query.in_("location", location)

        if compensation_type:
            query = query.in_("compensation_type", compensation_type)

        if cash_amount_min is not None:
            query = query.gte("cash_amount_max", cash_amount_min)

        if cash_amount_max is not None:
            query = query.lte("cash_amount_min", cash_amount_max)

        if deliverables:
            query = query.contains("deliverables", deliverables)

        # only_qualified is harder to filter strictly in SQL without user profile data,
        # but if implemented, it could check min_engagement_rate etc. We'll skip for now
        # or implement it via the service layer if needed.

        start = (page - 1) * page_size
        end = start + page_size - 1
        result = await self._execute(query.range(start, end))

        rows = result.data or []
        return [Campaign.from_row(row) for row in rows], result.count or 0

    async def insert_campaign(self, data: dict) -> Campaign | None:
        rows = await self.insert("campaigns", data)
        return Campaign.from_row(rows[0]) if rows else None

    async def update_campaign(self, campaign_id: str, data: dict) -> Campaign | None:
        rows = await self.update("campaigns", data, {"id": campaign_id})
        return Campaign.from_row(rows[0]) if rows else None

    async def delete_campaign(self, campaign_id: str) -> None:
        await self.delete("campaigns", {"id": campaign_id})

    async def fetch_application_counts(self, campaign_ids: list[str]) -> dict[str, dict]:
        if not campaign_ids:
            return {}

        rows = await self.select(
            "campaign_applications",
            columns="campaign_id,status",
            filters={"campaign_id": campaign_ids},
        )

        counts: dict[str, dict] = {}
        for row in rows:
            cid = row["campaign_id"]
            entry = counts.setdefault(cid, {"applicant_count": 0, "accepted_count": 0})
            entry["applicant_count"] += 1
            if row["status"] == "accepted":
                entry["accepted_count"] += 1

        return counts

    async def get_locations(self) -> list[str]:
        # Fetch all active locations and deduplicate in Python
        result = await self._execute(
            (await self._table("campaigns"))
            .select("location")
            .eq("status", "active")
        )
        rows = result.data or []
        # Extract location string, filter nulls/empties, trim, and unique
        seen = set()
        locations = []
        for row in rows:
            loc = (row.get("location") or "").strip()
            if loc and loc.lower() not in seen:
                seen.add(loc.lower())
                locations.append(loc)
        return sorted(locations)
