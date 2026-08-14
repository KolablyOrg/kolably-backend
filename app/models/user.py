"""
User profile domain model.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.enums import UserRole


@dataclass
class UserProfile:
    """User profile domain model — internal representation."""
    id: str  # profiles.id
    auth_id: str  # auth.users.id
    email: str
    role: UserRole
    full_name: str | None = None
    avatar_url: str | None = None
    phone: str | None = None
    is_active: bool = True
    email_confirmed_at: datetime | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime | None = None
    totp_secret_encrypted: str | None = None
    totp_enabled: bool = False

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "UserProfile":
        return cls(
            id=row["id"],
            auth_id=row["auth_id"],
            email=row["email"],
            role=UserRole(row["role"]),
            full_name=row.get("full_name"),
            avatar_url=row.get("avatar_url"),
            phone=row.get("phone"),
            is_active=row.get("is_active", True),
            email_confirmed_at=row.get("email_confirmed_at"),
            created_at=row["created_at"],
            updated_at=row.get("updated_at"),
            totp_secret_encrypted=row.get("totp_secret_encrypted"),
            totp_enabled=row.get("totp_enabled", False),
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "auth_id": self.auth_id,
            "email": self.email,
            "role": self.role.value,
            "full_name": self.full_name,
            "avatar_url": self.avatar_url,
            "phone": self.phone,
            "is_active": self.is_active,
            "email_confirmed_at": self.email_confirmed_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
