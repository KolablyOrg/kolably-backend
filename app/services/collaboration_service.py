from fastapi import HTTPException, status

from app.repositories.business_repo import BusinessRepository
from app.repositories.collaboration_repo import CollaborationRepository
from app.repositories.creator_repo import CreatorRepository


async def _get_creator_id_for_user(
    profile_id: str,
    *,
    repo: CreatorRepository | None = None,
) -> str:
    repo = repo or CreatorRepository()
    creator_id = await repo.get_id_by_profile_id(profile_id)
    if not creator_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator profile not found",
        )
    return creator_id


async def _get_business_id_for_user(
    profile_id: str,
    *,
    repo: BusinessRepository | None = None,
) -> str:
    repo = repo or BusinessRepository()
    business_id = await repo.get_id_by_profile_id(profile_id)
    if not business_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found",
        )
    return business_id


def _row_to_collaboration_response(row: dict) -> dict:
    return {
        "id": row["id"],
        "campaign_id": row["campaign_id"],
        "creator_id": row["creator_id"],
        "business_id": row["business_id"],
        "status": row["status"],
        "content_submissions": [],
        "affiliate_url": row.get("affiliate_url"),
        "created_at": row["created_at"],
        "completed_at": row.get("completed_at"),
    }


async def list_collaborations(
    profile_id: str,
    role: str,
    page: int = 1,
    page_size: int = 20,
    *,
    repo: CollaborationRepository | None = None,
    creator_repo: CreatorRepository | None = None,
    business_repo: BusinessRepository | None = None,
) -> dict:
    repo = repo or CollaborationRepository()

    if role == "creator":
        creator_id = await _get_creator_id_for_user(profile_id, repo=creator_repo)
        rows, total = await repo.list_by_creator(
            creator_id=creator_id,
            page=page,
            page_size=page_size,
        )
    elif role == "business":
        business_id = await _get_business_id_for_user(profile_id, repo=business_repo)
        rows, total = await repo.list_by_business(
            business_id=business_id,
            page=page,
            page_size=page_size,
        )
    else:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    items = [_row_to_collaboration_response(row) for row in rows]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_collaboration(
    collaboration_id: str,
    *,
    repo: CollaborationRepository | None = None,
) -> dict:
    repo = repo or CollaborationRepository()
    row = await repo.get_by_id(collaboration_id)

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collaboration not found",
        )

    submissions_raw = await repo.list_submissions(collaboration_id)
    submissions = [
        {
            "id": sub["id"],
            "collaboration_id": sub["collaboration_id"],
            "content_url": sub["content_url"],
            "platform": sub["platform"],
            "views": sub.get("views"),
            "likes": sub.get("likes"),
            "comments": sub.get("comments"),
            "synced_at": sub.get("synced_at"),
            "submitted_at": sub["submitted_at"],
        }
        for sub in submissions_raw
    ]

    resp = _row_to_collaboration_response(row)
    resp["content_submissions"] = submissions
    return resp
