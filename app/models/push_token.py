"""
Push token domain model.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class PushToken:
    """One Expo push token, tied to a single profile + app install."""

    id: str
    profile_id: str
    expo_push_token: str
    platform: str
    created_at: datetime
    last_used_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "PushToken":
        return cls(
            id=row["id"],
            profile_id=row["profile_id"],
            expo_push_token=row["expo_push_token"],
            platform=row["platform"],
            created_at=row["created_at"],
            last_used_at=row["last_used_at"],
        )
