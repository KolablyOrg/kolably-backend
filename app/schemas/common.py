"""
Shared / common Pydantic schemas.
"""

from typing import Generic, TypeVar

from pydantic import BaseModel


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str


class UploadResponse(BaseModel):
    """Public URL returned after a media upload completes."""
    url: str


class PaginationParams(BaseModel):
    """Standard pagination query parameters."""
    page: int = 1
    page_size: int = 20


T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated list response."""
    items: list[T]
    total: int
    page: int
    page_size: int
