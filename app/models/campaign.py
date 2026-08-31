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


def _parse_json_list(value: Any) -> list:
    import json

    if value is None:
        return []
    if isinstance(value, str):
        return json.loads(value) if value else []
    if isinstance(value, list):
        return value
    return []


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
    # Brief / objective & audience
    platforms: list[str] = field(default_factory=list)
    product_promoted: str | None = None
    audience_age_range: str | None = None
    audience_gender: str | None = None
    audience_location: str | None = None
    audience_interests: str | None = None
    key_messaging: str | None = None
    dos: str | None = None
    donts: str | None = None
    reference_image_urls: list[str] = field(default_factory=list)
    content_due_at: datetime | None = None
    # Computed
    applicant_count: int | None = None
    accepted_count: int | None = None
    posted_count: int | None = None
    pending_applicant_count: int | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any], counts: dict[str, Any] | None = None) -> "Campaign":
        deliverables_data = _parse_json_list(row.get("deliverables"))
        deliverables = [CampaignDeliverable.from_dict(d) for d in deliverables_data]

        platforms_raw = _parse_json_list(row.get("platforms"))
        platforms = [str(p) for p in platforms_raw]

        refs_raw = _parse_json_list(row.get("reference_image_urls"))
        reference_image_urls = [str(u) for u in refs_raw]

        campaign = cls(
            id=row["id"],
            business_id=row["business_id"],
            title=row["title"],
            objective=CampaignObjective(row["objective"]),
            description=row["description"] or "",
            cover_image_url=row.get("cover_image_url"),
            deliverables=deliverables,
            compensation_type=CompensationType(row["compensation_type"]) if row.get("compensation_type") else None,
            cash_amount_min=row.get("cash_amount_min"),
            cash_amount_max=row.get("cash_amount_max"),
            free_product_description=row.get("free_product_description"),
            creator_category=row.get("creator_category", "") or "",
            follower_range_min=row.get("follower_range_min"),
            follower_range_max=row.get("follower_range_max"),
            min_engagement_rate=row.get("min_engagement_rate"),
            location=row.get("location", "") or "",
            max_creators=row.get("max_creators") or 1,
            additional_requirements=row.get("additional_requirements"),
            deadline=row.get("deadline"),
            status=CampaignStatus(row["status"]),
            created_at=row["created_at"],
            platforms=platforms,
            product_promoted=row.get("product_promoted"),
            audience_age_range=row.get("audience_age_range"),
            audience_gender=row.get("audience_gender"),
            audience_location=row.get("audience_location"),
            audience_interests=row.get("audience_interests"),
            key_messaging=row.get("key_messaging"),
            dos=row.get("dos"),
            donts=row.get("donts"),
            reference_image_urls=reference_image_urls,
            content_due_at=row.get("content_due_at"),
        )

        if counts:
            campaign.applicant_count = counts.get("applicant_count")
            campaign.accepted_count = counts.get("accepted_count")
            campaign.posted_count = counts.get("posted_count")
            campaign.pending_applicant_count = counts.get("pending_applicant_count")

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
            "platforms": self.platforms,
            "product_promoted": self.product_promoted,
            "audience_age_range": self.audience_age_range,
            "audience_gender": self.audience_gender,
            "audience_location": self.audience_location,
            "audience_interests": self.audience_interests,
            "key_messaging": self.key_messaging,
            "dos": self.dos,
            "donts": self.donts,
            "reference_image_urls": self.reference_image_urls,
            "content_due_at": self.content_due_at,
        }
