from app.models.application import CampaignApplication
from app.repositories.base import BaseRepository


class ApplicationRepository(BaseRepository):
    async def get_by_id(self, application_id: str) -> CampaignApplication | None:
        row = await self.select_one(
            "campaign_applications",
            columns="*",
            filters={"id": application_id},
        )
        return CampaignApplication.from_row(row) if row else None

    async def get_existing(self, campaign_id: str, creator_id: str) -> CampaignApplication | None:
        row = await self.select_one(
            "campaign_applications",
            columns="*",
            filters={"campaign_id": campaign_id, "creator_id": creator_id},
        )
        return CampaignApplication.from_row(row) if row else None

    async def list_by_creator(
        self,
        creator_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[CampaignApplication], int]:
        query = (
            (await self._table("campaign_applications"))
            .select(
                "*, "
                "campaigns!campaign_applications_campaign_id_fkey("
                "  *, "
                "  businesses!campaigns_business_id_fkey(id, business_name, logo_url)"
                ")",
                count="exact",
            )
            .eq("creator_id", creator_id)
            .order("created_at", desc=True)
        )

        start = (page - 1) * page_size
        end = start + page_size - 1
        result = await self._execute(query.range(start, end))

        rows = result.data or []
        return [CampaignApplication.from_row(row) for row in rows], result.count or 0

    async def list_by_business(
        self,
        business_id: str,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[CampaignApplication], int]:
        query = (
            (await self._table("campaign_applications"))
            .select(
                "*, "
                "campaigns!campaign_applications_campaign_id_fkey!inner(*, business_id), "
                "creators!campaign_applications_creator_id_fkey("
                "id, name, profile_photo_url, follower_count, niche)",
                count="exact",
            )
            .eq("campaigns.business_id", business_id)
            .order("created_at", desc=True)
        )

        if status:
            query = query.eq("status", status)

        start = (page - 1) * page_size
        end = start + page_size - 1
        result = await self._execute(query.range(start, end))

        rows = result.data or []
        return [CampaignApplication.from_row(row) for row in rows], result.count or 0

    async def list_by_campaign(
        self,
        campaign_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[CampaignApplication], int]:
        query = (
            (await self._table("campaign_applications"))
            .select(
                "*, creators(id,name,profile_photo_url,follower_count,niche,city,engagement_rate)",
                count="exact",
            )
            .eq("campaign_id", campaign_id)
            .order("created_at", desc=True)
        )

        start = (page - 1) * page_size
        end = start + page_size - 1
        result = await self._execute(query.range(start, end))

        rows = result.data or []
        return [CampaignApplication.from_row(row) for row in rows], result.count or 0

    async def insert_application(self, data: dict) -> CampaignApplication | None:
        rows = await self.insert("campaign_applications", data)
        return CampaignApplication.from_row(rows[0]) if rows else None

    async def update_status(self, application_id: str, status: str) -> CampaignApplication | None:
        rows = await self.update(
            "campaign_applications", {"status": status}, {"id": application_id}
        )
        return CampaignApplication.from_row(rows[0]) if rows else None

    async def update_application(
        self, application_id: str, data: dict
    ) -> CampaignApplication | None:
        rows = await self.update("campaign_applications", data, {"id": application_id})
        return CampaignApplication.from_row(rows[0]) if rows else None

    async def delete_application(self, application_id: str) -> None:
        await self.delete("campaign_applications", {"id": application_id})
