"""
Application-wide enums.
"""

from enum import StrEnum


class UserRole(StrEnum):
    CREATOR = "creator"
    BUSINESS = "business"
    SUPERADMIN = "superadmin"


class CampaignStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    CLOSED = "closed"
    COMPLETED = "completed"


class CompensationType(StrEnum):
    CASH = "cash"
    PRODUCT = "product"
    CASH_AND_PRODUCT = "cash_and_product"


class Platform(StrEnum):
    INSTAGRAM = "instagram"
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"


class ContentType(StrEnum):
    POST = "post"
    REEL = "reel"
    STORY = "story"
    VIDEO = "video"
    SHORT = "short"


class CampaignObjective(StrEnum):
    BRAND_AWARENESS = "brand_awareness"
    PRODUCT_LAUNCH = "product_launch"
    FOOT_TRAFFIC = "foot_traffic"
    USER_GENERATED_CONTENT = "user_generated_content"
    SALES_CONVERSION = "sales_conversion"
    EVENT_PROMOTION = "event_promotion"
    OTHER = "other"


class ApplicationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    REVISION_REQUESTED = "revision_requested"


class ApplicationDirection(StrEnum):
    CREATOR_APPLIED = "creator_applied"
    BUSINESS_INVITED = "business_invited"


class CollaborationStatus(StrEnum):
    ACTIVE = "active"
    CONTENT_SUBMITTED = "content_submitted"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class NotificationType(StrEnum):
    APPLICATION_RECEIVED = "application_received"
    APPLICATION_ACCEPTED = "application_accepted"
    APPLICATION_REJECTED = "application_rejected"
    REVISION_REQUESTED = "revision_requested"
    APPLICATION_RESUBMITTED = "application_resubmitted"
    CAMPAIGN_INVITE_RECEIVED = "campaign_invite_received"
    NEW_MESSAGE = "new_message"
    COLLABORATION_COMPLETED = "collaboration_completed"
