import uuid
from fastapi import APIRouter, File, UploadFile, Depends, HTTPException, status

from app.core.dependencies import get_current_user
from app.core.supabase import get_supabase_admin_client
from app.schemas.users import UserInToken

router = APIRouter(prefix="/upload", tags=["Upload"])

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
BUCKET_NAME = "media"

@router.post("/image")
async def upload_image(
    file: UploadFile = File(...),
    user: UserInToken = Depends(get_current_user),
):
    """
    Upload an image to Supabase Storage and return its public URL.
    """
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type. Must be JPEG, PNG, WEBP, or GIF."
        )
    
    # Read file content to check size and upload
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Maximum size is 5MB."
        )

    # Generate a unique path: e.g. avatars/123e4567-e89b-12d3/uuid.jpg
    ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "jpg"
    file_path = f"avatars/{user.id}/{uuid.uuid4().hex}.{ext}"

    try:
        # Upload to Supabase Storage
        supabase = await get_supabase_admin_client()
        # Ensure we pass the correct kwargs; Supabase python client for storage expects bytes and content-type
        res = await supabase.storage.from_(BUCKET_NAME).upload(
            path=file_path,
            file=contents,
            file_options={"content-type": file.content_type}
        )
        
        # Get public URL
        public_url = await supabase.storage.from_(BUCKET_NAME).get_public_url(file_path)
        
        return {"url": public_url}
    except Exception as e:
        error_msg = str(e)
        if "Bucket not found" in error_msg or "row-level security" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Storage error: {error_msg}. Please ensure bucket '{BUCKET_NAME}' exists."
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload image: {error_msg}"
        )
