"""
Handlers for server-to-server callbacks Meta sends to the app (as opposed to
`instagram_service.py`, which is calls *we* make outward to Meta's Graph API).
"""

import uuid
from datetime import UTC, datetime

from app.core.config import settings
from app.core.exceptions import BadRequestError
from app.core.meta_signed_request import InvalidSignedRequestError, parse_signed_request
from app.repositories.creator_repo import CreatorRepository
from app.repositories.data_deletion_repo import DataDeletionRepository
from app.repositories.profile_repo import ProfileRepository

_STATUS_BASE_URL = "https://kolably.com/data-deletion/status"

_ANONYMIZED_CREATOR_FIELDS = {
    "name": "Deleted Creator",
    "username": None,
    "bio": None,
    "profile_photo_url": None,
    "instagram_handle": None,
    "website": None,
    "city": None,
    "instagram_user_id": None,
    "instagram_access_token": None,
    "instagram_token_expires_at": None,
    "instagram_synced_at": None,
}


def _verify(signed_request: str) -> dict:
    """Shared verification step for both Meta callbacks below. Tries both
    known app secrets — see meta_signed_request.py's docstring on why it's
    ambiguous which one Meta actually signs with."""
    try:
        return parse_signed_request(
            signed_request, secrets=[settings.APP_SECRET, settings.INSTAGRAM_APP_SECRET]
        )
    except InvalidSignedRequestError as e:
        raise BadRequestError(str(e))


async def handle_data_deletion(
    signed_request: str,
    *,
    creator_repo: CreatorRepository | None = None,
    profile_repo: ProfileRepository | None = None,
    deletion_repo: DataDeletionRepository | None = None,
) -> dict:
    """Meta's Data Deletion Request Callback.

    Anonymizes the matching creator/profile (rows are kept, not hard-deleted,
    so FK references from collaborations/applications/messages stay intact —
    see the Account Deletion & Data Retention Policy in
    Kolably_Legal_Documentation_Kit.docx), and returns the
    `{url, confirmation_code}` shape Meta requires.
    """
    payload = _verify(signed_request)
    instagram_user_id = str(payload["user_id"])

    creator_repo = creator_repo or CreatorRepository()
    profile_repo = profile_repo or ProfileRepository()
    deletion_repo = deletion_repo or DataDeletionRepository()

    creator = await creator_repo.get_by_instagram_user_id(instagram_user_id)
    status = "no_matching_account"

    if creator:
        await creator_repo.delete_portfolio_by_creator_id(creator["id"])
        await creator_repo.anonymize(creator["id"], dict(_ANONYMIZED_CREATOR_FIELDS))
        await profile_repo.anonymize(
            creator["profile_id"], f"deleted-{creator['profile_id']}@deleted.kolably.com"
        )
        status = "completed"

    confirmation_code = uuid.uuid4().hex
    now = datetime.now(UTC).isoformat()
    await deletion_repo.insert_request({
        "confirmation_code": confirmation_code,
        "instagram_user_id": instagram_user_id,
        "profile_id": creator["profile_id"] if creator else None,
        "status": status,
        "completed_at": now,
    })

    return {
        "url": f"{_STATUS_BASE_URL}/{confirmation_code}",
        "confirmation_code": confirmation_code,
    }


async def handle_deauthorize(
    signed_request: str,
    *,
    creator_repo: CreatorRepository | None = None,
) -> dict:
    """Meta's Deauthorize Callback — fires when a user revokes Kolably's
    Instagram access without going through a full data-deletion request.

    Lighter-touch than `handle_data_deletion`: the stored access token is
    already dead at Meta's end regardless, so this just clears the
    connection fields immediately (rather than waiting for the next Graph
    API call to fail) — name/bio/photo/portfolio are untouched, since
    disconnecting isn't a request to delete data.
    """
    payload = _verify(signed_request)
    instagram_user_id = str(payload["user_id"])

    creator_repo = creator_repo or CreatorRepository()
    creator = await creator_repo.get_by_instagram_user_id(instagram_user_id)

    if creator:
        await creator_repo.clear_instagram_connection(creator["id"])

    return {"status": "ok"}
