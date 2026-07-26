from app.repositories.base import BaseRepository


class ApplicationRepository(BaseRepository):
    async def get_by_id(self, application_id: str) -> dict | None:
        return await self.select_one(
            "campaign_applications",
            columns="*",
            filters={"id": application_id},
        )

    async def get_existing(self, campaign_id: str, creator_id: str) -> dict | None:
        return await self.select_one(
            "campaign_applications",
            columns="id",
            filters={"campaign_id": campaign_id, "creator_id": creator_id},
        )

    async def list_by_creator(
        self,
        creator_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        query = (
            self._table("campaign_applications")
            .select(
                "*,",
                "campaigns!campaign_applications_campaign_id_fkey(*),",
                "businesses!campaigns_business_id_fkey(*,",
                "profiles!businesses_profile_id_fkey(business_name, logo_url))",
            )
            .eq("creator_id", creator_id)
        )

        start = (page - 1) * page_size
        end = start + page_size - 1
        result = query.range(start, end).execute()

        return result.data or [], result.count or 0

    async def list_by_business(
        self,
        business_id: str,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        query = (
            self._table("campaign_applications")
            .select(
                "*,",
                "campaigns!campaign_applications_campaign_id_fkey(*, business_id),",
                "creators!campaign_applications_creator_id_fkey(",
                "id, name, profile_photo_url, follower_count, niche)",
            )
            .eq("campaigns.business_id", business_id)
        )

        if status:
            query = query.eq("status", status)

        start = (page - 1) * page_size
        end = start + page_size - 1
        result = query.range(start, end).execute()

        return result.data or [], result.count or 0

    async def list_by_campaign(self, campaign_id: str) -> list[dict]:
        query = (
            self._table("campaign_applications")
            .select("*, creators(id,name,profile_photo_url,follower_count,niche)")
            .eq("campaign_id", campaign_id)
        )

        result = query.execute()
        return result.data or []

    async def insert_application(self, data: dict) -> dict | None:
        rows = await self.insert("campaign_applications", data)
        return rows[0] if rows else None
