"""
Domain models package — internal data structures.

Models represent the internal domain entities and are separate from
API schemas (request/response contracts). Services convert between
models and schemas.
"""

from app.models.application import CampaignApplication
from app.models.business import Business
from app.models.campaign import Campaign, CampaignDeliverable
from app.models.chat import Conversation, Message
from app.models.collaboration import Collaboration
from app.models.creator import Creator, PortfolioItem
from app.models.notification import Notification
from app.models.user import UserProfile

__all__ = [
    "Campaign",
    "CampaignDeliverable",
    "Creator",
    "PortfolioItem",
    "Business",
    "CampaignApplication",
    "Collaboration",
    "Conversation",
    "Message",
    "Notification",
    "UserProfile",
]
