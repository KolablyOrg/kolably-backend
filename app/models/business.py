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
    description: str | None = None
    address: str | None = None
    logo_url: str | None = None
    instagram_handle: str | None = None
    website: str | None = None
    owner_name: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    is_verified: bool = False
    business_name: str | None = None
    city: str | None = None
    category: str | None = None
    legal_entity_name: str | None = None
    business_type: str | None = None
    pan_number: str | None = None
    gst_number: str | None = None
    business_proof_document_url: str | None = None
    kyb_status: str = "unverified"
    kyb_submitted_at: datetime | None = None
    kyb_verified_at: datetime | None = None
    kyb_rejection_reason: str | None = None
    notification_preferences: dict[str, Any] = field(
        default_factory=lambda: {
            "new_applications": True,
            "creator_messages": True,
            "payment_alerts": True,
        }
    )
    is_discoverable: bool = True

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Business":
        return cls(
            id=row["id"],
            profile_id=row["profile_id"],
            business_name=row.get("business_name"),
            city=row.get("city"),
            category=row.get("category"),
            description=row.get("description"),
            address=row.get("address"),
            logo_url=row.get("logo_url"),
            instagram_handle=row.get("instagram_handle"),
            website=row.get("website"),
            owner_name=row.get("owner_name", ""),
            created_at=row["created_at"],
            is_verified=row.get("is_verified", False),
            legal_entity_name=row.get("legal_entity_name"),
            business_type=row.get("business_type"),
            pan_number=row.get("pan_number"),
            gst_number=row.get("gst_number"),
            business_proof_document_url=row.get("business_proof_document_url"),
            kyb_status=row.get("kyb_status", "unverified"),
            kyb_submitted_at=row.get("kyb_submitted_at"),
            kyb_verified_at=row.get("kyb_verified_at"),
            kyb_rejection_reason=row.get("kyb_rejection_reason"),
            notification_preferences=row.get("notification_preferences")
            or {
                "new_applications": True,
                "creator_messages": True,
                "payment_alerts": True,
            },
            is_discoverable=row.get("is_discoverable", True),
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
            "instagram_handle": self.instagram_handle,
            "website": self.website,
            "owner_name": self.owner_name,
            "created_at": self.created_at,
            "is_verified": self.is_verified,
            "legal_entity_name": self.legal_entity_name,
            "business_type": self.business_type,
            "pan_number": self.pan_number,
            "gst_number": self.gst_number,
            "business_proof_document_url": self.business_proof_document_url,
            "kyb_status": self.kyb_status,
            "kyb_submitted_at": self.kyb_submitted_at,
            "kyb_verified_at": self.kyb_verified_at,
            "kyb_rejection_reason": self.kyb_rejection_reason,
            "notification_preferences": self.notification_preferences,
            "is_discoverable": self.is_discoverable,
        }
