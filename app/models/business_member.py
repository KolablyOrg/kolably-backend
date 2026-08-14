"""
Business team-member domain model.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class BusinessMember:
    """A team member (or pending invite) attached to a business account."""

    id: str
    business_id: str
    role: str  # "owner" | "editor" | "viewer" — a co-owner invite here, not the original businesses.profile_id row
    invited_email: str
    status: str = "pending"  # "pending" | "active" | "revoked"
    profile_id: str | None = None
    invited_by: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    accepted_at: datetime | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "BusinessMember":
        return cls(
            id=row["id"],
            business_id=row["business_id"],
            role=row["role"],
            invited_email=row["invited_email"],
            status=row.get("status", "pending"),
            profile_id=row.get("profile_id"),
            invited_by=row.get("invited_by"),
            created_at=row["created_at"],
            accepted_at=row.get("accepted_at"),
        )
