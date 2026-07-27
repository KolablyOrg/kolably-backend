"""
Schemas for Meta-originated server-to-server callbacks.
"""

from pydantic import BaseModel


class DataDeletionResponse(BaseModel):
    """Exact shape Meta's Data Deletion Request Callback requires."""

    url: str
    confirmation_code: str
