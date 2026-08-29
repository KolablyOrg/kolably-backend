from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import verify_cron_secret
from app.services import creator_service

router = APIRouter()


@router.post("/snapshot-stats", status_code=status.HTTP_200_OK)
async def snapshot_creator_stats(
    authorized: bool = Depends(verify_cron_secret),
):
    """
    Triggered daily (see `app/core/scheduler.py` — an in-process scheduler
    also calls this same logic automatically, since nothing external is
    wired up to hit this endpoint) to re-fetch every connected creator's
    live Instagram stats and snapshot follower count / engagement rate /
    views count into `creator_stats_history`. Kept as a real HTTP endpoint
    too so it can still be triggered manually or from an external
    scheduler if one gets set up later.
    """
    if not authorized:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid cron secret",
        )

    result = await creator_service.refresh_all_instagram_stats()

    return {
        "status": "success",
        "message": "Refreshed and snapshotted Instagram stats for all connected creators.",
        **result,
    }
