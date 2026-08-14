"""
Landing-page waitlist capture — public, no auth. Plain storage (see
migrations/20260814000003_create_waitlist_signups.sql's comment) — no
mailing-list service is wired up yet.
"""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, EmailStr

from app.repositories.base import BaseRepository

router = APIRouter()


class WaitlistJoinRequest(BaseModel):
    email: EmailStr
    role: Literal["creator", "business"]


class WaitlistJoinResponse(BaseModel):
    message: str


@router.post("/", response_model=WaitlistJoinResponse)
async def join_waitlist(data: WaitlistJoinRequest):
    """Idempotent — re-submitting the same email is treated as success, not
    an error the landing-page form needs to handle specially."""
    repo = BaseRepository()
    existing = await repo.select_one("waitlist_signups", filters={"email": data.email})
    if not existing:
        await repo.insert("waitlist_signups", {"email": data.email, "role": data.role})
    return WaitlistJoinResponse(message="You're on the list!")
