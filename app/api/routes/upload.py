import io
import logging
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError

from app.core.dependencies import get_current_user
from app.core.supabase import get_supabase_admin_client
from app.schemas.user import UserInToken

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["Upload"])

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
BUCKET_NAME = "media"

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
# logos, and KYB verification documents from all landing in one
# undifferentiated "avatars" folder.
UploadPurpose = Literal["avatar", "business-logo", "verification-doc"]

@router.post("/image")
async def upload_image(
    file: UploadFile = File(...),
    purpose: UploadPurpose = Form("avatar"),
    user: UserInToken = Depends(get_current_user),
):
    """
    Upload an image to Supabase Storage and return its public URL.
    """
    # Read file content to check size and upload
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Maximum size is 5MB."
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
            detail="Unsupported file type. Must be JPEG, PNG, WEBP, or GIF."
        )
    content_type, ext = _ALLOWED_FORMATS[real_format]

    # Generate a unique path: e.g. business-logo/123e4567-e89b-12d3/uuid.jpg
    file_path = f"{purpose}/{user.id}/{uuid.uuid4().hex}.{ext}"

    try:
        # Upload to Supabase Storage
        supabase = await get_supabase_admin_client()
        # Ensure we pass the correct kwargs; Supabase python client for storage expects bytes and content-type
        await supabase.storage.from_(BUCKET_NAME).upload(
            path=file_path,
            file=contents,
            file_options={"content-type": content_type}
        )

        # Get public URL
        public_url = await supabase.storage.from_(BUCKET_NAME).get_public_url(file_path)

        return {"url": public_url}
    except Exception as e:
        error_msg = str(e)
        logger.exception("Image upload failed for user_id=%s purpose=%s: %s", user.id, purpose, error_msg)
        if "Bucket not found" in error_msg or "row-level security" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Storage error: {error_msg}. Please ensure bucket '{BUCKET_NAME}' exists."
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to upload image. Please try again."
        )
