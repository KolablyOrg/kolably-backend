import io
import logging
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError

from app.core.dependencies import get_current_user
from app.schemas.common import UploadResponse
from app.schemas.user import UserInToken
from app.services import storage_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["Upload"])

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

# Real-format → (content-type, extension). Keyed by what Pillow actually
# decodes the bytes as, never the client-supplied filename/Content-Type
# header — those are trivially spoofable (e.g. a renamed HTML/script file
# claiming `Content-Type: image/png`).
_ALLOWED_FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
    "GIF": ("image/gif", "gif"),
}

# Top-level folder per upload purpose — keeps creator avatars, business
# logos, campaign assets, and KYB verification documents separated in the
# shared `media` bucket.
UploadPurpose = Literal[
    "avatar",
    "business-logo",
    "campaign-cover",
    "campaign-reference",
    "verification-doc",
]


@router.post("/image", response_model=UploadResponse)
async def upload_image(
    file: UploadFile = File(...),
    purpose: UploadPurpose = Form("avatar"),
    user: UserInToken = Depends(get_current_user),
):
    """
    Upload an image to the S3 media bucket and return its public URL.
    """
    # Read file content to check size and upload
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large. Maximum size is 5MB."
        )

    # Verify the bytes actually decode as an image, and derive the real
    # content-type/extension from that — never trust the client's
    # Content-Type header or filename extension.
    try:
        with Image.open(io.BytesIO(contents)) as img:
            img.verify()
            real_format = img.format
    except (UnidentifiedImageError, OSError, ValueError):
        real_format = None

    if real_format not in _ALLOWED_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type. Must be JPEG, PNG, WEBP, or GIF.",
        )
    content_type, ext = _ALLOWED_FORMATS[real_format]

    # Normalise the client-supplied filename onto the real extension derived
    # from the decoded bytes — a renamed HTML file forced to `.jpg` must not
    # end up keyed with a misleading suffix (and served with the wrong name).
    stem = (file.filename or "image").rsplit(".", 1)[0][:80] or "image"
    filename = f"{stem}.{ext}"

    # Server-side upload into the S3 `media` bucket. The bytes are stored
    # under `{purpose}/{user.id}/…`, matching the existing folder convention.
    key = await storage_service.upload_bytes(
        namespace=purpose,
        owner_id=user.id,
        filename=filename,
        data=contents,
        content_type=content_type,
    )

    return {"url": storage_service.public_url(key)}
