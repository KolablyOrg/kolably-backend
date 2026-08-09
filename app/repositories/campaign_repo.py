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
        budget_ranges: list[str] | None = None,
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

        if budget_ranges:
            # We want to support multi-select budgets (e.g. "under_10k" AND "10k_25k").
            # A campaign matches if its range overlaps with ANY selected budget range.
            # E.g. for 10k-25k, campaign matches if max >= 10k AND min <= 25k.
            budget_clauses = []
            for r in budget_ranges:
                if r == "under_10k":
                    budget_clauses.append("cash_amount_max.lte.10000")
                elif r == "10k_25k":
                    budget_clauses.append("and(cash_amount_min.lte.25000,cash_amount_max.gte.10000)")
                elif r == "25k_50k":
                    budget_clauses.append("and(cash_amount_min.lte.50000,cash_amount_max.gte.25000)")
                elif r == "50k_plus":
                    budget_clauses.append("cash_amount_min.gte.50000")
            
            if budget_clauses:
                query = query.or_(",".join(budget_clauses))

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
            entry = counts.setdefault(
                cid, {"applicant_count": 0, "accepted_count": 0, "posted_count": 0}
            )
            entry["applicant_count"] += 1
            if row["status"] == "accepted":
                entry["accepted_count"] += 1

        posted = await self.fetch_posted_counts(campaign_ids)
        for cid, posted_count in posted.items():
            entry = counts.setdefault(
                cid, {"applicant_count": 0, "accepted_count": 0, "posted_count": 0}
            )
            entry["posted_count"] = posted_count

        return counts

    async def fetch_posted_counts(self, campaign_ids: list[str]) -> dict[str, int]:
        """Count collaborations with ≥1 content submission per campaign."""
        if not campaign_ids:
            return {}

        collab_rows = await self.select(
            "collaborations",
            columns="id,campaign_id",
            filters={"campaign_id": campaign_ids},
        )
        if not collab_rows:
            return {}

        collab_to_campaign = {r["id"]: r["campaign_id"] for r in collab_rows}
        collab_ids = list(collab_to_campaign.keys())
        sub_rows = await self.select(
            "content_submissions",
            columns="collaboration_id",
            filters={"collaboration_id": collab_ids},
        )

        posted_collabs: set[str] = set()
        for row in sub_rows:
            cid = row.get("collaboration_id")
            if cid:
                posted_collabs.add(cid)

        posted_counts: dict[str, int] = {cid: 0 for cid in campaign_ids}
        for collab_id in posted_collabs:
            campaign_id = collab_to_campaign.get(collab_id)
            if campaign_id:
                posted_counts[campaign_id] = posted_counts.get(campaign_id, 0) + 1
        return posted_counts

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
