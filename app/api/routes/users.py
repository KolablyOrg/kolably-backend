"""
User routes — shared operations for both account types.
"""

from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_user
from app.schemas.auth import MessageResponse
from app.schemas.user import UserInToken
from app.services import auth_service

router = APIRouter()


@router.get("/me")
async def get_current_user_profile(user: UserInToken = Depends(get_current_user)):
    """Get the currently authenticated user's profile."""
    return await auth_service.get_user_profile(user.auth_id)


@router.delete("/me", response_model=MessageResponse)
async def delete_current_user(user: UserInToken = Depends(get_current_user)):
    """Deactivate / delete the current user's account."""
    return await auth_service.delete_user_account(profile_id=user.id)
