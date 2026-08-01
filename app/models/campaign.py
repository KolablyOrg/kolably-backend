"""
Campaign domain models.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.enums import (
    CampaignObjective,
    CampaignStatus,
    CompensationType,
    ContentType,
    Platform,
)


@dataclass
class CampaignDeliverable:
    """A single deliverable item within a campaign."""
    platform: Platform
    content_type: ContentType
    quantity: int
    description: str | None = None
    required: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CampaignDeliverable":
        return cls(
            platform=Platform(data["platform"]),
            content_type=ContentType(data["content_type"]),
            quantity=data["quantity"],
            description=data.get("description"),
            required=data.get("required", True),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform.value,
            "content_type": self.content_type.value,
            "quantity": self.quantity,
            "description": self.description,
            "required": self.required,
        }


@dataclass
class Campaign:
    """Campaign domain model — internal representation."""
    id: str
    business_id: str
    title: str
    objective: CampaignObjective
    description: str
    cover_image_url: str | None = None
    deliverables: list[CampaignDeliverable] = field(default_factory=list)
    compensation_type: CompensationType | None = None
    cash_amount_min: float | None = None
    cash_amount_max: float | None = None
    free_product_description: str | None = None
    creator_category: str = ""
    follower_range_min: int | None = None
    follower_range_max: int | None = None
    min_engagement_rate: float | None = None
    location: str = ""
    max_creators: int = 1
    additional_requirements: str | None = None
    deadline: datetime | None = None
    status: CampaignStatus = CampaignStatus.DRAFT
    created_at: datetime = field(default_factory=datetime.utcnow)
    applicant_count: int | None = None
    accepted_count: int | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any], counts: dict[str, Any] | None = None) -> "Campaign":
        import json
        deliverables_data = row.get("deliverables") or []
        if isinstance(deliverables_data, str):
            deliverables_data = json.loads(deliverables_data) if deliverables_data else []

        deliverables = [CampaignDeliverable.from_dict(d) for d in deliverables_data]

        campaign = cls(
            id=row["id"],
            business_id=row["business_id"],
            title=row["title"],
            objective=CampaignObjective(row["objective"]),
            description=row["description"],
            cover_image_url=row.get("cover_image_url"),
            deliverables=deliverables,
            compensation_type=CompensationType(row["compensation_type"]) if row.get("compensation_type") else None,
            cash_amount_min=row.get("cash_amount_min"),
            cash_amount_max=row.get("cash_amount_max"),
            free_product_description=row.get("free_product_description"),
            creator_category=row.get("creator_category", ""),
            follower_range_min=row.get("follower_range_min"),
            follower_range_max=row.get("follower_range_max"),
            min_engagement_rate=row.get("min_engagement_rate"),
            location=row.get("location", ""),
            max_creators=row.get("max_creators", 1),
            additional_requirements=row.get("additional_requirements"),
            deadline=row.get("deadline"),
            status=CampaignStatus(row["status"]),
            created_at=row["created_at"],
        )

        if counts:
            campaign.applicant_count = counts.get("applicant_count")
            campaign.accepted_count = counts.get("accepted_count")

        return campaign

    def to_row(self) -> dict[str, Any]:
        """Convert to dict for database insert/update."""
        return {
            "id": self.id,
            "business_id": self.business_id,
            "title": self.title,
            "objective": self.objective.value,
            "description": self.description,
            "cover_image_url": self.cover_image_url,
            "deliverables": [d.to_dict() for d in self.deliverables],
            "compensation_type": self.compensation_type.value if self.compensation_type else None,
            "cash_amount_min": self.cash_amount_min,
            "cash_amount_max": self.cash_amount_max,
            "free_product_description": self.free_product_description,
            "creator_category": self.creator_category,
            "follower_range_min": self.follower_range_min,
            "follower_range_max": self.follower_range_max,
            "min_engagement_rate": self.min_engagement_rate,
            "location": self.location,
            "max_creators": self.max_creators,
            "additional_requirements": self.additional_requirements,
            "deadline": self.deadline,
            "status": self.status.value,
            "created_at": self.created_at,
        }
