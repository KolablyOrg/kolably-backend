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
    user_id: str  # profiles.id
    type: NotificationType
    title: str
    body: str
    data: dict[str, Any] = field(default_factory=dict)
    read_at: datetime | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Notification":
        import json
        data = row.get("data") or {}
        if isinstance(data, str):
            data = json.loads(data) if data else {}

        return cls(
            id=row["id"],
            user_id=row["user_id"],
            type=NotificationType(row["type"]),
            title=row["title"],
            body=row["body"],
            data=data,
            read_at=row.get("read_at"),
            created_at=row["created_at"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "type": self.type.value,
            "title": self.title,
            "body": self.body,
            "data": self.data,
            "read_at": self.read_at,
            "created_at": self.created_at,
        }
