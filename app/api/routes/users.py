"""
User routes — shared operations for both account types.
"""

from fastapi import APIRouter, HTTPException, status

router = APIRouter()


@router.get("/me")
async def get_current_user():
    """Get the currently authenticated user's profile."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Not implemented",
    )


@router.patch("/me")
async def update_current_user():
    """Update the currently authenticated user's base profile."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Not implemented",
    )


@router.delete("/me")
async def delete_current_user():
    """Deactivate / delete the current user's account."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Not implemented",
    )
