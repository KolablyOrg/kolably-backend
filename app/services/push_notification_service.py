"""
Expo push notification sender.

Called as a side effect of `notification_service.create_notification` — one
in-app notification write fans out to every device (push token) the
recipient is logged in on. Never raises, same contract as
`create_notification` itself: a push failing to send must never fail the
action that triggered the underlying notification.
"""

import logging

import httpx

from app.repositories.push_token_repo import PushTokenRepository

logger = logging.getLogger(__name__)

_EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


async def _post(messages: list[dict]) -> list[dict]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            _EXPO_PUSH_URL,
            json=messages,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
    response.raise_for_status()
    return response.json().get("data", [])


async def send_push_to_profile(
    profile_id: str,
    title: str,
    body: str,
    data: dict | None = None,
    *,
    repo: PushTokenRepository | None = None,
) -> None:
    """Send `title`/`body` to every device registered for `profile_id`.

    A profile with no registered devices (push never enabled, or the app
    was never opened on this build) is the common case, not an error —
    returns immediately.
    """
    repo = repo or PushTokenRepository()
    try:
        tokens = await repo.list_tokens_for_profile(profile_id)
        if not tokens:
            return

        messages = [
            {
                "to": t.expo_push_token,
                "title": title,
                "body": body,
                "sound": "default",
                "data": data or {},
            }
            for t in tokens
        ]
        # A profile realistically has a handful of devices at most — Expo's
        # 100-messages-per-request cap is never a real constraint here, so
        # no chunking.
        receipts = await _post(messages)

        for token, receipt in zip((t.expo_push_token for t in tokens), receipts):
            if receipt.get("status") == "error" and receipt.get("details", {}).get("error") == "DeviceNotRegistered":
                # App uninstalled, or a stale token from a wiped simulator —
                # Expo will keep erroring on it forever, so stop sending.
                await repo.delete_by_token(token)
    except Exception:
        logger.exception("Failed to send push notification (profile_id=%s)", profile_id)


async def register_token(
    profile_id: str, token: str, platform: str, *, repo: PushTokenRepository | None = None
) -> None:
    repo = repo or PushTokenRepository()
    await repo.upsert_token(profile_id, token, platform)


async def unregister_token(token: str, *, repo: PushTokenRepository | None = None) -> None:
    """Best-effort — called during logout, which itself tolerates failure."""
    repo = repo or PushTokenRepository()
    try:
        await repo.delete_by_token(token)
    except Exception:
        logger.exception("Failed to unregister push token")
