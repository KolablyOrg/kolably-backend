from app.models.creator import Creator, PortfolioItem
from app.repositories.base import BaseRepository


def _sanitize_search_term(term: str) -> str:
    """Strip PostgREST `or_()` grammar breakers and LIKE wildcards from user input."""
    cleaned = term.strip()
    for ch in (",", "(", ")", ".", "%", "_", "*", '"', "'", "&"):
        cleaned = cleaned.replace(ch, " ")
    return " ".join(cleaned.split())


class CreatorRepository(BaseRepository):
    async def get_by_id(self, creator_id: str) -> Creator | None:
        row = await self.select_one(
            "creators",
            columns="*",
            filters={"id": creator_id},
        )
        return Creator.from_row(row) if row else None

    async def get_by_profile_id(self, profile_id: str) -> Creator | None:
        row = await self.select_one(
            "creators",
            columns="*",
            filters={"profile_id": profile_id},
        )
        return Creator.from_row(row) if row else None

    async def get_by_instagram_user_id(self, instagram_user_id: str) -> Creator | None:
        row = await self.select_one(
            "creators",
            columns="*",
            filters={"instagram_user_id": instagram_user_id},
        )
        return Creator.from_row(row) if row else None

    async def get_id_by_profile_id(self, profile_id: str) -> str | None:
        row = await self.select_one(
            "creators",
            columns="id",
            filters={"profile_id": profile_id},
        )
        return row["id"] if row else None

    async def list_filtered(
        self,
        search: str | None = None,
        niche: str | None = None,
        city: list[str] | None = None,
        follower_min: int | None = None,
        follower_max: int | None = None,
        engagement_min: float | None = None,
        verified_only: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Creator], int]:
        query = (
            (await self._table("creators"))
            .select("*", count="exact")
            # Brands must not see creators who opted out of discovery.
            .eq("is_discoverable", True)
        )

        if search:
            term = _sanitize_search_term(search)
            if term:
                query = query.or_(
                    ",".join(
                        [
                            f"name.ilike.%{term}%",
                            f"username.ilike.%{term}%",
                            f"instagram_handle.ilike.%{term}%",
                            f"niche.ilike.%{term}%",
                            f"city.ilike.%{term}%",
                        ]
                    )
                )
        if niche:
            # Case-insensitive so a "Food" pill still matches stored "food".
            query = query.ilike("niche", f"%{niche}%")
        if city:
            # Same pattern as campaign feed locations: exact values from
            # GET /creators/locations, multi-select via repeated query params.
            cleaned = [c.strip() for c in city if c and c.strip()]
            if cleaned:
                query = query.in_("city", cleaned)
        if follower_min is not None:
            query = query.gte("follower_count", follower_min)
        if follower_max is not None:
            query = query.lte("follower_count", follower_max)
        if engagement_min is not None:
            # Sparse Instagram sync data: keep unknown rates visible rather than
            # silently dropping most creators when brands pick an engagement floor.
            query = query.or_(
                f"engagement_rate.is.null,engagement_rate.gte.{engagement_min}"
            )
        if verified_only:
            # "Instagram insights confirmed" — connected accounts have a user id.
            query = query.not_.is_("instagram_user_id", "null")

        start = (page - 1) * page_size
        end = start + page_size - 1
        result = await self._execute(query.range(start, end))

        rows = result.data or []
        return [Creator.from_row(row) for row in rows], result.count or 0

    async def get_locations(self) -> list[str]:
        """Distinct cities from discoverable creators — drives brand Discover pills."""
        result = await self._execute(
            (await self._table("creators"))
            .select("city")
            .eq("is_discoverable", True)
        )
        rows = result.data or []
        seen: set[str] = set()
        locations: list[str] = []
        for row in rows:
            loc = (row.get("city") or "").strip()
            if not loc:
                continue
            key = loc.lower()
            if key in seen:
                continue
            seen.add(key)
            locations.append(loc)
        return sorted(locations, key=str.lower)

    async def get_niches(self) -> list[str]:
        """Distinct niches from discoverable creators — drives brand Discover pills."""
        result = await self._execute(
            (await self._table("creators"))
            .select("niche")
            .eq("is_discoverable", True)
        )
        rows = result.data or []
        seen: set[str] = set()
        niches: list[str] = []
        for row in rows:
            value = (row.get("niche") or "").strip()
            if not value:
                continue
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            niches.append(value)
        return sorted(niches, key=str.lower)

    async def insert_creator(self, data: dict) -> Creator | None:
        rows = await self.insert("creators", data)
        return Creator.from_row(rows[0]) if rows else None

    async def insert_portfolio_items(self, items: list[dict]) -> list[PortfolioItem]:
        if not items:
            return []
        rows = await self.insert("portfolio_items", items)
        return [PortfolioItem.from_row(row) for row in rows]

    async def anonymize(self, creator_id: str, data: dict) -> Creator | None:
        """Scrub PII from a creator row in place — used for Meta's Data
        Deletion Callback. Rows are kept (not hard-deleted) so FK references
        from collaborations/applications/messages don't break; see
        Kolably_Legal_Documentation_Kit.docx's Account Deletion policy."""
        rows = await self.update("creators", data, {"id": creator_id})
        return Creator.from_row(rows[0]) if rows else None

    async def delete_portfolio_by_creator_id(self, creator_id: str) -> list[dict]:
        return await self.delete("portfolio_items", {"creator_id": creator_id})

    async def clear_instagram_connection(self, creator_id: str) -> Creator | None:
        """Clear a stale Instagram connection — used by Meta's Deauthorize
        Callback, when a user revokes access without a full data-deletion
        request. Lighter-touch than `anonymize`: only the connection fields
        are cleared, name/bio/photo/portfolio stay untouched."""
        rows = await self.update("creators", {
            "instagram_user_id": None,
            "instagram_access_token": None,
            "instagram_token_expires_at": None,
            "instagram_synced_at": None,
        }, {"id": creator_id})
        return Creator.from_row(rows[0]) if rows else None

    async def update_by_profile_id(self, profile_id: str, data: dict) -> Creator | None:
        rows = await self.update("creators", data, {"profile_id": profile_id})
        return Creator.from_row(rows[0]) if rows else None

    async def update_creator(self, creator_id: str, data: dict) -> Creator | None:
        rows = await self.update("creators", data, {"id": creator_id})
        return Creator.from_row(rows[0]) if rows else None

    async def get_niche_by_profile_id(self, profile_id: str) -> str | None:
        row = await self.select_one(
            "creators",
            columns="niche",
            filters={"profile_id": profile_id},
        )
        return row.get("niche") if row else None

    async def get_portfolio_item(self, item_id: str) -> PortfolioItem | None:
        row = await self.select_one(
            "portfolio_items",
            columns="*",
            filters={"id": item_id},
        )
        return PortfolioItem.from_row(row) if row else None

    async def insert_portfolio_item(self, data: dict) -> PortfolioItem | None:
        rows = await self.insert("portfolio_items", data)
        return PortfolioItem.from_row(rows[0]) if rows else None

    async def get_portfolio_items_by_post_links(
        self, creator_id: str, post_links: list[str]
    ) -> list[PortfolioItem]:
        if not post_links:
            return []
        rows = await self.select(
            "portfolio_items",
            columns="*",
            filters={"creator_id": creator_id, "post_link": post_links},
        )
        return [PortfolioItem.from_row(row) for row in rows]

    async def update_portfolio_item(self, item_id: str, data: dict) -> PortfolioItem | None:
        rows = await self.update("portfolio_items", data, {"id": item_id})
        return PortfolioItem.from_row(rows[0]) if rows else None

    async def delete_portfolio_item(self, item_id: str, creator_id: str) -> list[dict]:
        return await self.delete("portfolio_items", {"id": item_id, "creator_id": creator_id})

    async def bulk_delete_portfolio_items(self, item_ids: list[str], creator_id: str) -> list[dict]:
        query = (await self._table("portfolio_items")).delete().eq("creator_id", creator_id).in_("id", item_ids)
        result = await self._execute(query)
        return result.data or []

    async def update_portfolio_item(self, item_id: str, data: dict) -> PortfolioItem | None:
        rows = await self.update("portfolio_items", data, {"id": item_id})
        return PortfolioItem.from_row(rows[0]) if rows else None

    async def list_portfolio(
        self,
        creator_id: str,
        media_type: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[PortfolioItem], int]:
        query = (
            (await self._table("portfolio_items"))
            .select("*", count="exact")
            .eq("creator_id", creator_id)
        )

        if media_type:
            query = query.eq("media_type", media_type)

        start = (page - 1) * page_size
        end = start + page_size - 1
        result = await self._execute(query.range(start, end))

        rows = result.data or []
        return [PortfolioItem.from_row(row) for row in rows], result.count or 0

    async def count_active_collaborations(self, creator_id: str) -> int:
        return await self.count(
            "collaborations",
            filters={"creator_id": creator_id, "status": "active"},
        )

    async def save_campaign(self, creator_id: str, campaign_id: str) -> None:
        """Idempotent — re-saving an already-saved campaign is a no-op."""
        await self.upsert(
            "saved_campaigns",
            {"creator_id": creator_id, "campaign_id": campaign_id},
        )

    async def unsave_campaign(self, creator_id: str, campaign_id: str) -> None:
        await self.delete(
            "saved_campaigns",
            {"creator_id": creator_id, "campaign_id": campaign_id},
        )

    async def list_saved_campaigns(
        self,
        creator_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        query = (
            (await self._table("saved_campaigns"))
            .select("*, campaigns!saved_campaigns_campaign_id_fkey(*)", count="exact")
            .eq("creator_id", creator_id)
        )

        start = (page - 1) * page_size
        end = start + page_size - 1
        result = await self._execute(query.range(start, end))

        return result.data or [], result.count or 0
