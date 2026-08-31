"""Authenticated global presence routes."""

from fastapi import APIRouter, Depends

from app.core.dependencies import require_role
from app.core.enums import UserRole
from app.schemas.presence import HeartbeatResponse
from app.schemas.user import UserInToken
from app.services import presence_service

router = APIRouter()


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(
    user: UserInToken = Depends(require_role(UserRole.CREATOR, UserRole.BUSINESS, UserRole.SUPERADMIN)),
) -> dict:
    return await presence_service.update_last_seen(user.id)
