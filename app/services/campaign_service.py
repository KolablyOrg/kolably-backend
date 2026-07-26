import json
from typing import Any

from fastapi import HTTPException, status

from app.core.enums import (
    ApplicationDirection,
    ApplicationStatus,
    CampaignStatus,
)
from app.repositories.application_repo import ApplicationRepository
from app.repositories.business_repo import BusinessRepository
from app.repositories.campaign_repo import CampaignRepository
from app.repositories.creator_repo import CreatorRepository
from app.schemas.application import ApplicationResponse, ApplicationWithCreator
from app.schemas.campaign import (
    CampaignCategoryResponse,
    CampaignCreateRequest,
    CampaignDeliverablesRequest,
    CampaignTargetingRequest,
    CampaignUpdateRequest,
)
from app.schemas.creator import CreatorSummary
from app.schemas.user import UserInToken


def _row_to_campaign_response(row: dict, counts: dict | None = None) -> dict:
    deliverables = row.get("deliverables") or []
    if isinstance(deliverables, str):
        deliverables = json.loads(deliverables) if deliverables else []

    response: dict[str, Any] = {
        "id": row["id"],
        "business_id": row["business_id"],
        "title": row["title"],
        "objective": row["objective"],
        "description": row["description"],
        "cover_image_url": row.get("cover_image_url"),
        "deliverables": deliverables,
        "compensation_type": row.get("compensation_type"),
        "cash_amount_min": row.get("cash_amount_min"),
        "cash_amount_max": row.get("cash_amount_max"),
        "free_product_description": row.get("free_product_description"),
        "creator_category": row.get("creator_category", ""),
        "follower_range_min": row.get("follower_range_min"),
        "follower_range_max": row.get("follower_range_max"),
        "min_engagement_rate": row.get("min_engagement_rate"),
        "location": row.get("location", ""),
        "max_creators": row.get("max_creators", 1),
        "additional_requirements": row.get("additional_requirements"),
        "deadline": row.get("deadline"),
        "status": row["status"],
        "created_at": row["created_at"],
    }
    if counts:
        response["applicant_count"] = counts.get("applicant_count")
        response["accepted_count"] = counts.get("accepted_count")
    return response


def _row_to_campaign_summary(row: dict, counts: dict | None = None) -> dict:
    response: dict[str, Any] = {
        "id": row["id"],
        "business_id": row["business_id"],
        "title": row["title"],
        "cover_image_url": row.get("cover_image_url"),
        "objective": row.get("objective"),
        "compensation_type": row.get("compensation_type"),
        "cash_amount_min": row.get("cash_amount_min"),
        "cash_amount_max": row.get("cash_amount_max"),
        "creator_category": row.get("creator_category", ""),
        "location": row.get("location", ""),
        "deadline": row.get("deadline"),
        "status": row["status"],
        "created_at": row["created_at"],
    }
    if counts:
        response["applicant_count"] = counts.get("applicant_count")
    return response


async def _get_business_id_for_user(profile_id: str) -> str:
    repo = BusinessRepository()
    business_id = await repo.get_id_by_profile_id(profile_id)
    if not business_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found",
        )
    return business_id


async def _ensure_campaign_owner(campaign_repo: CampaignRepository, campaign_id: str, business_id: str) -> dict:
    row = await campaign_repo.get_by_id(campaign_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )
    if row["business_id"] != business_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this campaign",
        )
    return row


async def create_campaign_step1(profile_id: str, data: CampaignCreateRequest) -> dict:
    business_id = await _get_business_id_for_user(profile_id)
    campaign_repo = CampaignRepository()

    insert_data = {
        "business_id": business_id,
        "title": data.title,
        "objective": data.objective.value,
        "description": data.description,
        "status": CampaignStatus.DRAFT.value,
        "deliverables": [],
        "creator_category": "",
        "location": "",
        "max_creators": 1,
    }

    row = await campaign_repo.insert_campaign(insert_data)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create campaign",
        )

    return _row_to_campaign_response(row)


async def update_campaign_deliverables(
    campaign_id: str,
    profile_id: str,
    data: CampaignDeliverablesRequest,
) -> dict:
    business_id = await _get_business_id_for_user(profile_id)
    campaign_repo = CampaignRepository()
    await _ensure_campaign_owner(campaign_repo, campaign_id, business_id)

    update_data: dict[str, Any] = {
        "deliverables": [d.model_dump() for d in data.deliverables],
        "compensation_type": data.compensation_type.value,
        **data.model_dump(exclude={"deliverables", "compensation_type"}, exclude_none=True),
    }

    row = await campaign_repo.update_campaign(campaign_id, update_data)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    return _row_to_campaign_response(row)


async def update_campaign_targeting(
    campaign_id: str,
    profile_id: str,
    data: CampaignTargetingRequest,
) -> dict:
    business_id = await _get_business_id_for_user(profile_id)
    campaign_repo = CampaignRepository()
    await _ensure_campaign_owner(campaign_repo, campaign_id, business_id)

    update_data: dict[str, Any] = data.model_dump(exclude_none=True)

    row = await campaign_repo.update_campaign(campaign_id, update_data)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    return _row_to_campaign_response(row)


async def update_campaign_general(
    campaign_id: str,
    profile_id: str,
    data: CampaignUpdateRequest,
) -> dict:
    business_id = await _get_business_id_for_user(profile_id)
    campaign_repo = CampaignRepository()
    row = await _ensure_campaign_owner(campaign_repo, campaign_id, business_id)

    update_data: dict[str, Any] = data.model_dump(exclude_none=True)
    if not update_data:
        return _row_to_campaign_response(row)

    if update_data.get("deliverables"):
        update_data["deliverables"] = [d.model_dump() for d in data.deliverables]
    if update_data.get("objective"):
        update_data["objective"] = data.objective.value
    if update_data.get("compensation_type"):
        update_data["compensation_type"] = data.compensation_type.value

    updated = await campaign_repo.update_campaign(campaign_id, update_data)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    return _row_to_campaign_response(updated)


async def publish_campaign(campaign_id: str, profile_id: str) -> dict:
    business_id = await _get_business_id_for_user(profile_id)
    campaign_repo = CampaignRepository()
    row = await _ensure_campaign_owner(campaign_repo, campaign_id, business_id)

    deliverables = row.get("deliverables") or []
    if isinstance(deliverables, str):
        deliverables = json.loads(deliverables) if deliverables else []

    required = {
        "title": row.get("title"),
        "objective": row.get("objective"),
        "description": row.get("description"),
        "deliverables": deliverables,
        "compensation_type": row.get("compensation_type"),
        "creator_category": row.get("creator_category"),
        "location": row.get("location"),
        "max_creators": row.get("max_creators"),
        "deadline": row.get("deadline"),
    }
    missing = [field for field, value in required.items() if not value]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"missing_fields": missing, "message": "Campaign is incomplete"},
        )

    updated = await campaign_repo.update_campaign(
        campaign_id, {"status": CampaignStatus.ACTIVE.value}
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    return _row_to_campaign_response(updated)


async def list_campaigns(
    search: str | None,
    category: str | None,
    recommended: bool | None,
    page: int,
    page_size: int,
    user: UserInToken | None = None,
) -> dict:
    campaign_repo = CampaignRepository()

    if recommended and user and user.role.value == "creator":
        creator_repo = CreatorRepository()
        niche = await creator_repo.get_niche_by_profile_id(user.id)
        if niche:
            category = niche

    rows, total = await campaign_repo.list_active(
        search=search,
        category=category,
        page=page,
        page_size=page_size,
    )

    counts = await campaign_repo.fetch_application_counts([r["id"] for r in rows])
    items = [_row_to_campaign_summary(r, counts.get(r["id"])) for r in rows]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_campaign(campaign_id: str) -> dict:
    campaign_repo = CampaignRepository()
    row = await campaign_repo.get_by_id(campaign_id)

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    counts = await campaign_repo.fetch_application_counts([campaign_id])
    return _row_to_campaign_response(row, counts.get(campaign_id))


async def delete_campaign(campaign_id: str, profile_id: str) -> dict:
    business_id = await _get_business_id_for_user(profile_id)
    campaign_repo = CampaignRepository()
    await _ensure_campaign_owner(campaign_repo, campaign_id, business_id)

    await campaign_repo.delete_campaign(campaign_id)
    return {"message": "Campaign deleted"}


CAMPAIGN_CATEGORIES: list[CampaignCategoryResponse] = [
    CampaignCategoryResponse(value="food", label="Food & Dining"),
    CampaignCategoryResponse(value="fashion", label="Fashion & Beauty"),
    CampaignCategoryResponse(value="tech", label="Technology"),
    CampaignCategoryResponse(value="travel", label="Travel & Tourism"),
    CampaignCategoryResponse(value="fitness", label="Fitness & Health"),
    CampaignCategoryResponse(value="lifestyle", label="Lifestyle"),
    CampaignCategoryResponse(value="entertainment", label="Entertainment"),
    CampaignCategoryResponse(value="education", label="Education"),
    CampaignCategoryResponse(value="real_estate", label="Real Estate"),
    CampaignCategoryResponse(value="automotive", label="Automotive"),
    CampaignCategoryResponse(value="finance", label="Finance"),
    CampaignCategoryResponse(value="other", label="Other"),
]


async def get_campaign_categories() -> list[CampaignCategoryResponse]:
    return CAMPAIGN_CATEGORIES


async def list_campaign_applications(campaign_id: str, profile_id: str) -> list[dict]:
    business_id = await _get_business_id_for_user(profile_id)
    campaign_repo = CampaignRepository()
    await _ensure_campaign_owner(campaign_repo, campaign_id, business_id)

    app_repo = ApplicationRepository()
    rows = await app_repo.list_by_campaign(campaign_id)

    items: list[dict] = []
    for row in rows:
        creator_data = row.pop("creators", {}) or {}
        creator = CreatorSummary(
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
            creator=creator,
        )
        items.append(app.model_dump(mode="json"))

    return items


async def invite_creator(
    campaign_id: str,
    profile_id: str,
    creator_id: str,
    message: str | None,
) -> dict:
    business_id = await _get_business_id_for_user(profile_id)
    campaign_repo = CampaignRepository()
    await _ensure_campaign_owner(campaign_repo, campaign_id, business_id)

    creator_repo = CreatorRepository()
    creator = await creator_repo.get_by_id(creator_id)
    if not creator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator not found",
        )

    app_repo = ApplicationRepository()
    existing = await app_repo.get_existing(campaign_id, creator_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Creator already has an application for this campaign",
        )

    insert_data = {
        "campaign_id": campaign_id,
        "creator_id": creator_id,
        "direction": ApplicationDirection.BUSINESS_INVITED.value,
        "message": message,
        "status": ApplicationStatus.PENDING.value,
    }

    row = await app_repo.insert_application(insert_data)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create invite",
        )

    return ApplicationResponse(
        id=row["id"],
        campaign_id=row["campaign_id"],
        creator_id=row["creator_id"],
        direction=row.get("direction", ApplicationDirection.BUSINESS_INVITED.value),
        message=row.get("message"),
        instagram_handle=row.get("instagram_handle"),
        example_content_url=row.get("example_content_url"),
        status=row["status"],
        revision_reason=row.get("revision_reason"),
        created_at=row["created_at"],
    ).model_dump(mode="json")
