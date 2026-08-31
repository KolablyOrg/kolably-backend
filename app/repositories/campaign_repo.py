import asyncio

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

    async def get_by_ids(self, campaign_ids: list[str]) -> list[Campaign]:
        if not campaign_ids:
            return []
        rows = await self.select("campaigns", columns="*", filters={"id": campaign_ids})
        return [Campaign.from_row(row) for row in rows]

    async def _business_ids_matching_name(self, term: str) -> list[str]:
        result = await self._execute(
            (await self._table("businesses"))
            .select("id")
            .ilike("business_name", f"%{term}%")
            .limit(50)
        )
        return [row["id"] for row in (result.data or []) if row.get("id")]

    async def _campaign_ids_with_deliverables(self, content_types: list[str]) -> list[str]:
        """Active campaign ids whose deliverables include any of `content_types`.

        `deliverables` is a JSONB array of objects
        (`[{"platform": "instagram", "content_type": "reel", ...}]`), so
        containment has to be checked against an object shape — matching it
        against a list of bare strings never returns anything. PostgREST also
        can't OR JSON containment clauses inside a single `or_()` (the braces
        and commas break its grammar), so each content type is resolved on its
        own and the ids are unioned here.
        """
        ids: list[str] = []
        seen: set[str] = set()
        for content_type in content_types:
            result = await self._execute(
                (await self._table("campaigns"))
                .select("id")
                .eq("status", "active")
                .contains("deliverables", [{"content_type": content_type}])
            )
            for row in result.data or []:
                campaign_id = row.get("id")
                if campaign_id and campaign_id not in seen:
                    seen.add(campaign_id)
                    ids.append(campaign_id)
        return ids

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
        budget_min: float | None = None,
        budget_max: float | None = None,
        deliverables: list[str] | None = None,
        only_qualified: bool | None = None,
        creator_follower_count: int | None = None,
        creator_engagement_rate: float | None = None,
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

        # Continuous range from the filter-sheet slider — unlike budget_ranges
        # above (multi-select bands, OR'd together), this is a single range so
        # both ends simply AND with everything else via normal gte/lte chaining.
        # Overlap semantics: campaign matches if its own range overlaps
        # [budget_min, budget_max] at all, not just if it sits fully inside it.
        if budget_min is not None:
            query = query.gte("cash_amount_max", budget_min)
        if budget_max is not None:
            query = query.lte("cash_amount_min", budget_max)

        if deliverables:
            matching_ids = await self._campaign_ids_with_deliverables(deliverables)
            if not matching_ids:
                return [], 0
            query = query.in_("id", matching_ids)

        if only_qualified:
            # The creator's own numbers come from the service layer. Campaigns
            # that set no bar stay visible, and a creator whose follower count
            # or engagement rate hasn't synced yet isn't filtered out on a
            # number we don't have — same treatment as creator discovery.
            if creator_follower_count is not None:
                query = query.or_(
                    f"follower_range_min.is.null,follower_range_min.lte.{int(creator_follower_count)}"
                )
            if creator_engagement_rate is not None:
                query = query.or_(
                    f"min_engagement_rate.is.null,min_engagement_rate.lte.{float(creator_engagement_rate)}"
                )

        start = (page - 1) * page_size
        end = start + page_size - 1
        result = await self._execute(query.range(start, end))

        rows = result.data or []
        return [Campaign.from_row(row) for row in rows], result.count or 0

    async def count_created_since(self, business_id: str, since) -> int:
        """Campaigns this business has created since `since`.

        Backs the "3 campaigns per month" free quota. Counting rows by
        `created_at` is why no usage-tracking table is needed — the
        campaigns themselves are the counter.

        Counts campaigns in ANY status, including drafts and closed ones:
        the quota is on the act of creating, not on holding an open
        campaign. Creating and immediately closing one still consumes the
        month's allowance, which is the intent.

        Known gap, accepted for now: `delete_campaign` removes the row, so
        create → delete → create can exceed the allowance. Not worth an
        anti-abuse mechanism at this stage — subscriptions are activated by
        hand and the customer base is small enough that it would be
        noticed. Revisit if self-serve billing ships.

        Uses a count-only select (`head=True`) so it doesn't pull every
        campaign row just to length it — this runs on every creation.
        """
        query = (
            (await self._table("campaigns"))
            .select("id", count="exact", head=True)
            .eq("business_id", business_id)
            .gte("created_at", since.isoformat())
        )
        result = await self._execute(query)
        return result.count or 0

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

        # Independent queries — run concurrently rather than paying two
        # sequential network round-trips.
        rows, posted = await asyncio.gather(
            self.select(
                "campaign_applications",
                columns="campaign_id,status",
                filters={"campaign_id": campaign_ids},
            ),
            self.fetch_posted_counts(campaign_ids),
        )

        counts: dict[str, dict] = {}
        for row in rows:
            cid = row["campaign_id"]
            entry = counts.setdefault(
                cid, {"applicant_count": 0, "accepted_count": 0, "posted_count": 0, "pending_applicant_count": 0}
            )
            entry["applicant_count"] += 1
            if row["status"] == "pending":
                entry["pending_applicant_count"] += 1
            if row["status"] == "accepted":
                entry["accepted_count"] += 1

        for cid, posted_count in posted.items():
            entry = counts.setdefault(
                cid, {"applicant_count": 0, "accepted_count": 0, "posted_count": 0, "pending_applicant_count": 0}
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

    async def get_budget_bounds(self) -> dict:
        """Cheapest and priciest cash budgets among active campaigns, so the
        filter-sheet slider can span real data instead of a guessed range.
        Product-only campaigns (no cash_amount_min/max) are naturally excluded
        since both columns are null for them.
        """
        result = await self._execute(
            (await self._table("campaigns"))
            .select("cash_amount_min,cash_amount_max")
            .eq("status", "active")
        )
        rows = result.data or []
        mins = [float(r["cash_amount_min"]) for r in rows if r.get("cash_amount_min") is not None]
        maxes = [float(r["cash_amount_max"]) for r in rows if r.get("cash_amount_max") is not None]
        return {
            "min": min(mins) if mins else None,
            "max": max(maxes) if maxes else None,
        }
