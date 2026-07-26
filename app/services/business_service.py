"""
Business service — profile CRUD, discovery.
"""

from fastapi import HTTPException, status

from app.core.supabase import get_supabase_admin_client
from app.schemas.business import BusinessResponse


async def list_businesses(
    search: str | None = None,
    category: str | None = None,
    city: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """List and filter businesses with pagination."""
    admin_client = get_supabase_admin_client()

    query = admin_client.table("businesses").select("*", count="exact")

    if search:
        query = query.ilike("business_name", f"%{search}%")
    if category:
        query = query.eq("category", category)
    if city:
        query = query.ilike("city", f"%{city}%")

    start = (page - 1) * page_size
    end = start + page_size - 1
    result = query.range(start, end).execute()

    rows = result.data or []
    items = []
    for row in rows:
        items.append({
            "id": row["id"],
            "user_id": row.get("profile_id"),
            "business_name": row["business_name"],
            "owner_name": row.get("owner_name", ""),
            "category": row.get("category", ""),
            "city": row.get("city", ""),
            "description": row.get("description"),
            "address": row.get("address"),
            "logo_url": row.get("logo_url"),
            "instagram_page": row.get("instagram_page"),
            "website": row.get("website"),
            "created_at": row["created_at"],
            "is_verified": row.get("is_verified", False),
        })

    return {
        "items": items,
        "total": result.count or 0,
        "page": page,
        "page_size": page_size,
    }


async def get_business_by_id(business_id: str) -> BusinessResponse | None:
    """Get a business by ID with profile info."""
    supabase = get_supabase_admin_client()

    result = (
        supabase.table("businesses")
        .select("*, profiles!businesses_profile_id_fkey(email, role)")
        .eq("id", business_id)
        .maybe_single()
        .execute()
    )

    if not result.data:
        return None

    data = result.data
    profile = data.pop("profiles", {})

    return BusinessResponse(
        id=data["id"],
        user_id=profile.get("id", data["profile_id"]),
        business_name=data["business_name"],
        owner_name=data.get("owner_name", ""),
        category=data.get("category", ""),
        city=data.get("city", ""),
        description=data.get("description"),
        address=data.get("address"),
        logo_url=data.get("logo_url"),
        instagram_page=data.get("instagram_page"),
        website=data.get("website"),
        created_at=data["created_at"],
        is_verified=data.get("is_verified", False),
    )


async def list_business_campaigns(
    business_id: str,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """List campaigns for a specific business."""
    admin_client = get_supabase_admin_client()

    query = (
        admin_client.table("campaigns")
        .select("*", count="exact")
        .eq("business_id", business_id)
    )

    if status:
        query = query.eq("status", status)

    start = (page - 1) * page_size
    end = start + page_size - 1
    result = query.range(start, end).execute()

    rows = result.data or []
    items = []
    for row in rows:
        items.append({
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
        })

    return {
        "items": items,
        "total": result.count or 0,
        "page": page,
        "page_size": page_size,
    }


async def get_business_stats(profile_id: str) -> dict:
    """Get stats for a business: total_reach, avg_engagement_rate."""
    admin_client = get_supabase_admin_client()

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

    business_id = result.data["id"]

    campaigns_result = (
        admin_client.table("campaigns")
        .select("id")
        .eq("business_id", business_id)
        .execute()
    )
    campaign_ids = [c["id"] for c in campaigns_result.data or []]

    total_reach = 0
    if campaign_ids:
        collabs_result = (
            admin_client.table("collaborations")
            .select("id")
            .in_("campaign_id", campaign_ids)
            .execute()
        )
        collab_ids = [c["id"] for c in collabs_result.data or []]

        if collab_ids:
            subs_result = (
                admin_client.table("content_submissions")
                .select("views,likes,comments")
                .in_("collaboration_id", collab_ids)
                .execute()
            )
            for sub in subs_result.data or []:
                total_reach += sub.get("views", 0) or 0

    return {
        "total_reach": total_reach,
        "reach_change_pct": 0.0,
        "avg_engagement_rate": 0.0,
        "engagement_series": [0.0] * 7,
    }
