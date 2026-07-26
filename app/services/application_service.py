from fastapi import HTTPException, status

from app.core.enums import ApplicationDirection
from app.repositories.application_repo import ApplicationRepository
from app.repositories.business_repo import BusinessRepository
from app.repositories.creator_repo import CreatorRepository
from app.schemas.application import ApplicationWithCampaign, ApplicationWithCreator
from app.schemas.business import BusinessSummary
from app.schemas.campaign import CampaignSummary
from app.schemas.creator import CreatorSummary


async def _get_creator_id_for_user(profile_id: str) -> str:
    repo = CreatorRepository()
    creator_id = await repo.get_id_by_profile_id(profile_id)
    if not creator_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator profile not found",
        )
    return creator_id


async def _get_business_id_for_user(profile_id: str) -> str:
    repo = BusinessRepository()
    business_id = await repo.get_id_by_profile_id(profile_id)
    if not business_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found",
        )
    return business_id


def _row_to_application_response(row: dict) -> dict:
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
    repo = ApplicationRepository()
    row = await repo.get_by_id(application_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )
    return _row_to_application_response(row)


async def list_my_applications(
    profile_id: str,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    creator_id = await _get_creator_id_for_user(profile_id)

    app_repo = ApplicationRepository()
    rows, total = await app_repo.list_by_creator(
        creator_id=creator_id,
        page=page,
        page_size=page_size,
    )

    items = []
    for row in rows:
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
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def list_business_applications(
    profile_id: str,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    business_id = await _get_business_id_for_user(profile_id)

    app_repo = ApplicationRepository()
    rows, total = await app_repo.list_by_business(
        business_id=business_id,
        status=status,
        page=page,
        page_size=page_size,
    )

    items = []
    for row in rows:
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
        "total": total,
        "page": page,
        "page_size": page_size,
    }
