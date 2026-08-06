from fastapi import APIRouter, Depends, HTTPException, status
from app.core.security import verify_cron_secret
from app.repositories.creator_repo import CreatorRepository

router = APIRouter()

@router.post("/snapshot-stats", status_code=status.HTTP_200_OK)
async def snapshot_creator_stats(
    authorized: bool = Depends(verify_cron_secret),
):
    """
    Triggered daily by a cron job to take a snapshot of all creators' follower count, 
    engagement rate, and views count and store it in `creator_stats_history`.
    """
    if not authorized:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid cron secret",
        )
    
    repo = CreatorRepository()
    await repo.snapshot_all_creators()
    
    return {"status": "success", "message": "Snapshotted all creator stats for today."}
