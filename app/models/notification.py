"""
Notification domain models.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.enums import NotificationType


@dataclass
class Notification:
    """Notification domain model — internal representation."""
    id: str
    profile_id: str  # profiles.id
    type: NotificationType
    title: str
    body: str
    related_id: str | None = None
    is_read: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Notification":
        return cls(
            id=row["id"],
            profile_id=row["profile_id"],
            type=NotificationType(row["type"]),
            title=row["title"],
            body=row["body"],
            related_id=row.get("related_id"),
            is_read=row.get("is_read", False),
            created_at=row["created_at"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "profile_id": self.profile_id,
            "type": self.type.value,
            "title": self.title,
            "body": self.body,
            "related_id": self.related_id,
            "is_read": self.is_read,
            "created_at": self.created_at,
        }
