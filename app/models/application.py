"""
Application domain models.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.enums import ApplicationDirection, ApplicationStatus


@dataclass
class CampaignApplication:
    """Campaign application domain model — internal representation."""

    id: str
    campaign_id: str
    creator_id: str
    direction: ApplicationDirection = ApplicationDirection.CREATOR_APPLIED
    message: str | None = None
    instagram_handle: str | None = None
    example_content_url: str | None = None
    status: ApplicationStatus = ApplicationStatus.PENDING
    revision_reason: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime | None = None
    # Deadline for a business_invited application; null for creator_applied.
    expires_at: datetime | None = None
    # Joined relation data — populated only when the repo query selects it
    # (e.g. list_by_creator joins campaigns + businesses + profiles).
    campaign: dict[str, Any] | None = None
    business: dict[str, Any] | None = None
    creator: dict[str, Any] | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "CampaignApplication":
        expires_at_raw = row.get("expires_at")
        expires_at = None
        if expires_at_raw:
            if isinstance(expires_at_raw, datetime):
                expires_at = expires_at_raw
            elif isinstance(expires_at_raw, str):
                try:
                    expires_at = datetime.fromisoformat(expires_at_raw.replace("Z", "+00:00"))
                except Exception:
                    expires_at = None

        return cls(
            id=row["id"],
            campaign_id=row["campaign_id"],
            creator_id=row["creator_id"],
            direction=ApplicationDirection(row.get("direction", "creator_applied")),
            message=row.get("message"),
            instagram_handle=row.get("instagram_handle"),
            example_content_url=row.get("example_content_url"),
            status=ApplicationStatus(row["status"]),
            revision_reason=row.get("revision_reason"),
            created_at=row["created_at"],
            updated_at=row.get("updated_at"),
            expires_at=expires_at,
            campaign=row.get("campaigns"),
            business=row.get("businesses"),
            creator=row.get("creators"),
        )

    def to_row(self) -> dict[str, Any]:
        """Convert to dict for database insert/update."""
        return {
            "id": self.id,
            "campaign_id": self.campaign_id,
            "creator_id": self.creator_id,
            "direction": self.direction.value,
            "message": self.message,
            "instagram_handle": self.instagram_handle,
            "example_content_url": self.example_content_url,
            "status": self.status.value,
            "revision_reason": self.revision_reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
        }
