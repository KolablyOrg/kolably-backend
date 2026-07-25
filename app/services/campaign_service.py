"""
Campaign service — CRUD, 4-step create/publish flow, feed, and invite logic.

All Supabase DB operations go through the service-role admin client.
"""

import json
from typing import Any

from fastapi import HTTPException, status
from supabase import Client

from app.core.enums import (
    ApplicationDirection,
    ApplicationStatus,
    CampaignStatus,
)
from app.core.supabase import get_supabase_admin_client
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

# ── Helpers ───────────────────────────────────────────


def _row_to_campaign_response(row: dict, counts: dict | None = None) -> dict:
    """Convert a Supabase campaigns row to a CampaignResponse dict."""
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
    """Convert a Supabase campaigns row to a CampaignSummary dict."""
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


def _get_business_id_for_user(admin_client: Client, profile_id: str) -> str:
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


def _fetch_counts(admin_client: Client, campaign_ids: list[str]) -> dict[str, dict]:
    """Return `{campaign_id: {applicant_count, accepted_count}}`."""
    if not campaign_ids:
        return {}
    result = (
        admin_client.table("campaign_applications")
        .select("campaign_id,status")
        .in_("campaign_id", campaign_ids)
        .execute()
    )
    accepted = ApplicationStatus.ACCEPTED.value
    counts: dict[str, dict] = {}
    for row in result.data or []:
        cid = row["campaign_id"]
        entry = counts.setdefault(cid, {"applicant_count": 0, "accepted_count": 0})
        entry["applicant_count"] += 1
        if row["status"] == accepted:
            entry["accepted_count"] += 1
    return counts


def _ensure_campaign_owner(admin_client: Client, campaign_id: str, business_id: str) -> dict:
    """Fetch a campaign and verify ownership. Returns the row."""
    result = (
        admin_client.table("campaigns")
        .select("*")
        .eq("id", campaign_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )
    row = result.data
    if row["business_id"] != business_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this campaign",
        )
    return row


# ── Step 1: Create Draft ──────────────────────────────


async def create_campaign_step1(profile_id: str, data: CampaignCreateRequest) -> dict:
    """Create a new draft campaign (Step 1)."""
    admin_client = get_supabase_admin_client()
    business_id = _get_business_id_for_user(admin_client, profile_id)

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

    result = admin_client.table("campaigns").insert(insert_data).execute()
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create campaign",
        )

    return _row_to_campaign_response(result.data[0])


# ── Step 2: Deliverables & Offer ──────────────────────


async def update_campaign_deliverables(
    campaign_id: str,
    profile_id: str,
    data: CampaignDeliverablesRequest,
) -> dict:
    """Patch deliverables and compensation (Step 2)."""
    admin_client = get_supabase_admin_client()
    business_id = _get_business_id_for_user(admin_client, profile_id)
    _ensure_campaign_owner(admin_client, campaign_id, business_id)

    update_data: dict[str, Any] = {
        "deliverables": [d.model_dump() for d in data.deliverables],
        "compensation_type": data.compensation_type.value,
        **data.model_dump(exclude={"deliverables", "compensation_type"}, exclude_none=True),
    }

    result = (
        admin_client.table("campaigns")
        .update(update_data)
        .eq("id", campaign_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    return _row_to_campaign_response(result.data[0])


# ── Step 3: Targeting ─────────────────────────────────


async def update_campaign_targeting(
    campaign_id: str,
    profile_id: str,
    data: CampaignTargetingRequest,
) -> dict:
    """Patch targeting criteria (Step 3)."""
    admin_client = get_supabase_admin_client()
    business_id = _get_business_id_for_user(admin_client, profile_id)
    _ensure_campaign_owner(admin_client, campaign_id, business_id)

    update_data: dict[str, Any] = data.model_dump(exclude_none=True)

    result = (
        admin_client.table("campaigns")
        .update(update_data)
        .eq("id", campaign_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    return _row_to_campaign_response(result.data[0])


# ── Step 4: General Update & Publish ───────────────────


async def update_campaign_general(
    campaign_id: str,
    profile_id: str,
    data: CampaignUpdateRequest,
) -> dict:
    """General patch — Step 4 (cover image / deadline) or any ad-hoc field update."""
    admin_client = get_supabase_admin_client()
    business_id = _get_business_id_for_user(admin_client, profile_id)
    row = _ensure_campaign_owner(admin_client, campaign_id, business_id)

    # Preserve enum types so `.value` works; nested models stay as models.
    update_data: dict[str, Any] = data.model_dump(exclude_none=True)
    if not update_data:
        return _row_to_campaign_response(row)

    if update_data.get("deliverables"):
        update_data["deliverables"] = [d.model_dump() for d in data.deliverables]
    if update_data.get("objective"):
        update_data["objective"] = data.objective.value
    if update_data.get("compensation_type"):
        update_data["compensation_type"] = data.compensation_type.value

    result = (
        admin_client.table("campaigns")
        .update(update_data)
        .eq("id", campaign_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    return _row_to_campaign_response(result.data[0])


async def publish_campaign(campaign_id: str, profile_id: str) -> dict:
    """Validate all required fields and flip status to `active`."""
    admin_client = get_supabase_admin_client()
    business_id = _get_business_id_for_user(admin_client, profile_id)
    row = _ensure_campaign_owner(admin_client, campaign_id, business_id)

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

    result = (
        admin_client.table("campaigns")
        .update({"status": CampaignStatus.ACTIVE.value})
        .eq("id", campaign_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    return _row_to_campaign_response(result.data[0])


# ── Read ──────────────────────────────────────────────


async def list_campaigns(
    search: str | None,
    category: str | None,
    recommended: bool | None,
    page: int,
    page_size: int,
    user: UserInToken | None = None,
) -> dict:
    """Paginated campaign feed with optional filters."""
    admin_client = get_supabase_admin_client()

    query = (
        admin_client.table("campaigns")
        .select("*", count="exact")
        .eq("status", CampaignStatus.ACTIVE.value)
    )

    if search:
        query = query.ilike("title", f"%{search}%")
    if category:
        query = query.eq("creator_category", category)

    if recommended and user and user.role.value == "creator":
        creator_result = (
            admin_client.table("creators")
            .select("niche")
            .eq("profile_id", user.id)
            .maybe_single()
            .execute()
        )
        niche = creator_result.data.get("niche") if creator_result.data else None
        if niche:
            query = query.eq("creator_category", niche)

    start = (page - 1) * page_size
    end = start + page_size - 1
    result = query.range(start, end).execute()

    rows = result.data or []
    counts = _fetch_counts(admin_client, [r["id"] for r in rows])
    items = [_row_to_campaign_summary(r, counts.get(r["id"])) for r in rows]

    return {
        "items": items,
        "total": result.count or 0,
        "page": page,
        "page_size": page_size,
    }


async def get_campaign(campaign_id: str) -> dict:
    """Get full campaign detail."""
    admin_client = get_supabase_admin_client()
    result = (
        admin_client.table("campaigns")
        .select("*")
        .eq("id", campaign_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    counts = _fetch_counts(admin_client, [campaign_id])
    return _row_to_campaign_response(result.data, counts.get(campaign_id))


async def delete_campaign(campaign_id: str, profile_id: str) -> dict:
    """Delete a campaign (owner only)."""
    admin_client = get_supabase_admin_client()
    business_id = _get_business_id_for_user(admin_client, profile_id)
    _ensure_campaign_owner(admin_client, campaign_id, business_id)

    admin_client.table("campaigns").delete().eq("id", campaign_id).execute()
    return {"message": "Campaign deleted"}


# ── Categories ────────────────────────────────────────


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


# ── Nested: Applications & Invite ─────────────────────


async def list_campaign_applications(campaign_id: str, profile_id: str) -> list[dict]:
    """List applications for a campaign (business owner only)."""
    admin_client = get_supabase_admin_client()
    business_id = _get_business_id_for_user(admin_client, profile_id)
    _ensure_campaign_owner(admin_client, campaign_id, business_id)

    result = (
        admin_client.table("campaign_applications")
        .select("*, creators(id,name,profile_photo_url,follower_count,niche)")
        .eq("campaign_id", campaign_id)
        .execute()
    )

    items: list[dict] = []
    for row in result.data or []:
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
    """Invite a creator to apply to a campaign."""
    admin_client = get_supabase_admin_client()
    business_id = _get_business_id_for_user(admin_client, profile_id)
    _ensure_campaign_owner(admin_client, campaign_id, business_id)

    creator_result = (
        admin_client.table("creators")
        .select("id")
        .eq("id", creator_id)
        .maybe_single()
        .execute()
    )
    if not creator_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator not found",
        )

    existing = (
        admin_client.table("campaign_applications")
        .select("id")
        .eq("campaign_id", campaign_id)
        .eq("creator_id", creator_id)
        .maybe_single()
        .execute()
    )
    if existing.data:
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

    result = (
        admin_client.table("campaign_applications")
        .insert(insert_data)
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create invite",
        )

    row = result.data[0]
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
