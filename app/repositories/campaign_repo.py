from app.models.campaign import Campaign
from app.repositories.base import BaseRepository


class CampaignRepository(BaseRepository):
    async def get_by_id(self, campaign_id: str) -> Campaign | None:
        row = await self.select_one(
            "campaigns",
            columns="*",
            filters={"id": campaign_id},
        )
        return Campaign.from_row(row) if row else None

    async def list_active(
        self,
        search: str | None = None,
        category: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Campaign], int]:
        query = (
            (await self._table("campaigns"))
            .select("*", count="exact")
            .eq("status", "active")
        )

        if search:
            query = query.ilike("title", f"%{search}%")
        if category:
            query = query.eq("creator_category", category)

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
