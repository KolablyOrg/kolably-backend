"""
Application service — apply, accept, reject.
"""

from fastapi import HTTPException, status

from app.core.enums import ApplicationDirection
from app.core.supabase import get_supabase_admin_client
from app.schemas.application import ApplicationWithCampaign, ApplicationWithCreator
from app.schemas.business import BusinessSummary
from app.schemas.campaign import CampaignSummary
from app.schemas.creator import CreatorSummary


def _get_creator_id_for_user(admin_client, profile_id: str) -> str:
    """Look up `creators.id` from `profiles.id`."""
    result = (
        admin_client.table("creators")
        .select("id")
        .eq("profile_id", profile_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator profile not found",
        )
    return result.data["id"]


def _get_business_id_for_user(admin_client, profile_id: str) -> str:
    """Look up `businesses.id` from `profiles.id`."""
    result = (
        admin_client.table("businesses")
        .select("id")
        .eq("profile_id", profile_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found",
        )
    return result.data["id"]


def _ensure_application_exists(admin_client, application_id: str) -> dict:
    """Fetch an application and verify it exists. Returns the row."""
    result = (
        admin_client.table("campaign_applications")
        .select("*")
        .eq("id", application_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )
    return result.data


def _row_to_application_response(row: dict) -> dict:
    """Convert a Supabase applications row to a ApplicationResponse dict."""
    return {
        "id": row["id"],
        "campaign_id": row["campaign_id"],
        "creator_id": row["creator_id"],
        "direction": row.get("direction", ApplicationDirection.CREATOR_APPLIED.value),
        "message": row.get("message"),
        "instagram_handle": row.get("instagram_handle"),
        "example_content_url": row.get("example_content_url"),
        "status": row["status"],
        "revision_reason": row.get("revision_reason"),
        "created_at": row["created_at"],
    }


async def get_application(application_id: str) -> dict:
    """Get application details."""
    admin_client = get_supabase_admin_client()
    row = _ensure_application_exists(admin_client, application_id)
    return _row_to_application_response(row)


async def list_my_applications(
    profile_id: str,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """List all applications sent by the current creator."""
    admin_client = get_supabase_admin_client()
    creator_id = _get_creator_id_for_user(admin_client, profile_id)

    query = (
        admin_client.table("campaign_applications")
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

    items = []
    for row in result.data or []:
        campaign_data = row.pop("campaigns", {}) or {}
        business_data = row.pop("businesses", {}) or {}
        profile_data = business_data.pop("profiles", {}) or {}

        campaign_summary = CampaignSummary(
            id=campaign_data.get("id", ""),
            business_id=campaign_data.get("business_id", ""),
            title=campaign_data.get("title", ""),
            cover_image_url=campaign_data.get("cover_image_url"),
            objective=campaign_data.get("objective", ""),
            compensation_type=campaign_data.get("compensation_type", ""),
            cash_amount_min=campaign_data.get("cash_amount_min"),
            cash_amount_max=campaign_data.get("cash_amount_max"),
            creator_category=campaign_data.get("creator_category", ""),
            location=campaign_data.get("location", ""),
            deadline=campaign_data.get("deadline"),
            status=campaign_data.get("status", ""),
            created_at=campaign_data.get("created_at", ""),
        )

        business_summary = BusinessSummary(
            id=business_data.get("id", ""),
            business_name=profile_data.get("business_name", ""),
            logo_url=business_data.get("logo_url"),
        )

        app = ApplicationWithCampaign(
            id=row["id"],
            campaign_id=row["campaign_id"],
            creator_id=row["creator_id"],
            direction=row.get("direction", ApplicationDirection.CREATOR_APPLIED.value),
            message=row.get("message"),
            instagram_handle=row.get("instagram_handle"),
            example_content_url=row.get("example_content_url"),
            status=row["status"],
            revision_reason=row.get("revision_reason"),
            created_at=row["created_at"],
            campaign=campaign_summary,
            business=business_summary,
        )
        items.append(app.model_dump(mode="json"))

    return {
        "items": items,
        "total": result.count or 0,
        "page": page,
        "page_size": page_size,
    }


async def list_business_applications(
    profile_id: str,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """List all applications for the business's campaigns."""
    admin_client = get_supabase_admin_client()
    business_id = _get_business_id_for_user(admin_client, profile_id)

    query = (
        admin_client.table("campaign_applications")
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

    items = []
    for row in result.data or []:
        creator_data = row.pop("creators", {}) or {}

        creator_summary = CreatorSummary(
            id=creator_data.get("id", ""),
            name=creator_data.get("name", ""),
            profile_photo_url=creator_data.get("profile_photo_url"),
            follower_count=creator_data.get("follower_count"),
            niche=creator_data.get("niche"),
        )

        app = ApplicationWithCreator(
            id=row["id"],
            campaign_id=row["campaign_id"],
            creator_id=row["creator_id"],
            direction=row.get("direction", ApplicationDirection.CREATOR_APPLIED.value),
            message=row.get("message"),
            instagram_handle=row.get("instagram_handle"),
            example_content_url=row.get("example_content_url"),
            status=row["status"],
            revision_reason=row.get("revision_reason"),
            created_at=row["created_at"],
            creator=creator_summary,
        )
        items.append(app.model_dump(mode="json"))

    return {
        "items": items,
        "total": result.count or 0,
        "page": page,
        "page_size": page_size,
    }
