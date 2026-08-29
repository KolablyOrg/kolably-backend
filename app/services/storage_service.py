"""
S3-backed object storage for creator/business media (avatars, campaign
assets, collab deliverables).

Uses `boto3` (the current AWS SDK for Python — boto3 >= 1.34, botocore's
bundled endpoint/retry config is what actually gets updated release to
release; there is no separate "v2" client to opt into for S3). boto3's S3
client is synchronous, and this app is async end-to-end (see auth_service,
business_access, etc.), so every network-hitting call here is pushed onto
a thread via `asyncio.to_thread` rather than awaited directly — otherwise
a slow S3 round-trip would block the event loop for every other request.

Uploads are never proxied through this backend. The client PUTs directly
to S3 using a presigned URL we hand back; we only ever see the resulting
object key. That keeps large media (video collab deliverables especially)
off our FastAPI workers entirely. `generate_upload_url` therefore returns
a key *before* the object exists — callers persist that key against the
relevant row (e.g. `creators.avatar_key`) optimistically, same as the
existing pattern of storing Instagram tokens before verifying them.

The boto3 client is module-level and created once (`_client()` memoizes
it) since it's thread-safe and cheap to reuse — creating a new client per
call re-does credential resolution and connection pool setup for nothing.
"""

import logging
import mimetypes
import uuid
from asyncio import to_thread
from functools import lru_cache

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)

PRESIGNED_URL_TTL_SECONDS = 900  # 15 min — long enough for a slow upload, short enough to not leak a durable link
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25MB; video deliverables go through a separate multipart flow, not this one

ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "video/mp4",
    "application/pdf",
}


@lru_cache(maxsize=1)
def _client():
    """Memoized boto3 S3 client — see module docstring for why this is cached."""
    return boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        # signature_version v4 is required for presigned URLs in any region
        # created after 2014 — explicit here so this doesn't silently break
        # if boto3's default ever changes.
        config=BotoConfig(signature_version="s3v4"),
    )


def public_url(key: str) -> str:
    """
    Public CDN URL for an object in the media bucket.

    The `media` bucket is public, so browsers (`<img src=…>`, CSS urls) read
    objects through Supabase's object-public endpoint with no presigning —
    this is what the frontend persists as `logo_url`/`profile_photo_url`.
    """
    return (
        f"{settings.SUPABASE_URL}/storage/v1/object/public/"
        f"{settings.AWS_S3_BUCKET}/{key}"
    )


def build_key(namespace: str, owner_id: str, filename: str) -> str:
    """
    Namespaced, collision-proof object key, e.g.
    `creators/<creator_id>/a1b2c3d4-original-name.jpg`.

    The uuid prefix (not a hash) is deliberate: filenames are user-supplied
    and we want the original name preserved for download-time display, but
    two uploads named `photo.jpg` from the same creator must never collide.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    safe_name = filename.rsplit(".", 1)[0][:80]  # keep keys bounded; S3 allows longer but this is plenty
    suffix = f".{ext}" if ext else ""
    return f"{namespace}/{owner_id}/{uuid.uuid4().hex[:12]}-{safe_name}{suffix}"


async def generate_upload_url(*, namespace: str, owner_id: str, filename: str, content_type: str) -> dict:
    """
    Returns a presigned PUT URL plus the key the object will land at.

    Content-type is validated here rather than left to S3 because a
    presigned PUT has no server-side hook to reject a bad type after the
    fact — this is the only checkpoint before the bytes are already stored.
    """
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported content type: {content_type}",
        )

    key = build_key(namespace, owner_id, filename)

    try:
        url = await to_thread(
            _client().generate_presigned_url,
            "put_object",
            Params={
                "Bucket": settings.AWS_S3_BUCKET,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=PRESIGNED_URL_TTL_SECONDS,
        )
    except ClientError as exc:
        logger.exception("generate_upload_url failed key=%s", key)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not prepare upload"
        ) from exc

    return {"upload_url": url, "key": key, "expires_in": PRESIGNED_URL_TTL_SECONDS}


async def generate_download_url(key: str, *, expires_in: int = PRESIGNED_URL_TTL_SECONDS) -> str:
    """Presigned GET — used for anything not served through a public CDN path (private deliverables, etc.)."""
    try:
        return await to_thread(
            _client().generate_presigned_url,
            "get_object",
            Params={"Bucket": settings.AWS_S3_BUCKET, "Key": key},
            ExpiresIn=expires_in,
        )
    except ClientError as exc:
        logger.exception("generate_download_url failed key=%s", key)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
        ) from exc


async def upload_bytes(
    *,
    namespace: str,
    owner_id: str,
    filename: str,
    data: bytes,
    content_type: str | None = None,
) -> str:
    """
    Upload bytes through S3 for trusted server-side callers. User-facing
    upload routes should retain their validation before calling this helper;
    the direct-PUT flow above is preferable for large browser uploads.
    """
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File too large")

    key = build_key(namespace, owner_id, filename)
    resolved_type = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"

    try:
        await to_thread(
            _client().put_object,
            Bucket=settings.AWS_S3_BUCKET,
            Key=key,
            Body=data,
            ContentType=resolved_type,
        )
    except ClientError as exc:
        logger.exception("upload_bytes failed key=%s", key)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Upload failed"
        ) from exc

    return key


async def delete_file(key: str) -> bool:
    """Idempotent by design — deleting a key that's already gone is not an error (S3 itself treats it this way)."""
    try:
        await to_thread(_client().delete_object, Bucket=settings.AWS_S3_BUCKET, Key=key)
    except ClientError as exc:
        logger.exception("delete_file failed key=%s", key)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Delete failed"
        ) from exc
    return True


async def delete_files(keys: list[str]) -> None:
    """
    Batched delete (S3 caps a single delete_objects call at 1000 keys) —
    used when e.g. a campaign is deleted and its whole asset folder needs
    to go with it, rather than N sequential delete_file calls.
    """
    if not keys:
        return
    for i in range(0, len(keys), 1000):
        chunk = keys[i : i + 1000]
        try:
            await to_thread(
                _client().delete_objects,
                Bucket=settings.AWS_S3_BUCKET,
                Delete={"Objects": [{"Key": k} for k in chunk], "Quiet": True},
            )
        except ClientError as exc:
            logger.exception("delete_files failed chunk_size=%d", len(chunk))
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail="Batch delete failed"
            ) from exc
