"""
Business domain models.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Business:
    """Business domain model — internal representation."""
    id: str
    profile_id: str
    business_name: str
    city: str
    category: str
    description: str | None = None
    address: str | None = None
    logo_url: str | None = None
    instagram_page: str | None = None
    website: str | None = None
    owner_name: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    is_verified: bool = False

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Business":
        return cls(
            id=row["id"],
            profile_id=row["profile_id"],
            business_name=row["business_name"],
            city=row["city"],
            category=row["category"],
            description=row.get("description"),
            address=row.get("address"),
            logo_url=row.get("logo_url"),
            instagram_page=row.get("instagram_page"),
            website=row.get("website"),
            owner_name=row.get("owner_name", ""),
            created_at=row["created_at"],
            is_verified=row.get("is_verified", False),
        )

    def to_row(self) -> dict[str, Any]:
        """Convert to dict for database insert/update."""
        return {
            "id": self.id,
            "profile_id": self.profile_id,
            "business_name": self.business_name,
            "city": self.city,
            "category": self.category,
            "description": self.description,
            "address": self.address,
            "logo_url": self.logo_url,
            "instagram_page": self.instagram_page,
            "website": self.website,
            "owner_name": self.owner_name,
            "created_at": self.created_at,
            "is_verified": self.is_verified,
        }
