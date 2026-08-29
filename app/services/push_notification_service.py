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

# Must match `ANDROID_CHANNEL_ID` in the mobile app's
# services/notifications/pushRegistration.ts. Android decides whether a
# notification produces a heads-up banner from the *channel's* importance,
# not from anything in the payload — so a message that names a channel the
# app never created falls back to a low-importance default and lands
# silently in the tray. That reads as "no notification arrived" to a user
# whose app is backgrounded.
_ANDROID_CHANNEL_ID = "messages_v2"


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
                # Android: without an explicit high priority, FCM is free to
                # batch/delay delivery while the app is backgrounded or the
                # device is dozing — which is exactly when a push matters
                # most. `channelId` picks the MAX-importance channel the app
                # registers; omitting it silently downgrades to a fallback
                # channel with no heads-up banner.
                "priority": "high",
                "channelId": _ANDROID_CHANNEL_ID,
                # iOS: bump the app-icon badge. Expo requires this per
                # message; there's no server-side counter, so this is a
                # presence indicator ("something new"), not an accurate
                # unread count — the app reconciles the real number from
                # GET /notifications/unread-count once opened.
                "badge": 1,
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


async def send_test_push(profile_id: str, *, repo: PushTokenRepository | None = None) -> dict:
    """Send a push to the caller's own devices and REPORT what happened.

    Deliberately the opposite contract to `send_push_to_profile`: that one
    swallows everything, because a failed push must never break the action
    that triggered it. That's correct for production and useless for
    debugging — "no notification arrived" gives you nothing to work with,
    since a profile with no registered devices and a profile whose devices
    all rejected the message look identical from the outside.

    This returns the device count and Expo's per-token receipt, and lets a
    transport failure raise, so the caller can tell apart:
      - no devices registered at all (the app never got a token to the
        server — the single most common cause)
      - Expo accepted the message (so any failure is downstream: APNs/FCM
        credentials, or the device itself)
      - Expo rejected a specific token (DeviceNotRegistered, etc.)
    """
    repo = repo or PushTokenRepository()
    tokens = await repo.list_tokens_for_profile(profile_id)
    if not tokens:
        return {
            "sent": False,
            "devices": 0,
            "detail": (
                "No push tokens registered for this account. The app registers one on "
                "login and on every app open, but only after notification permission is "
                "granted and a token can actually be derived — check the Device/"
                "Permission/Push token rows above for which of those hasn't happened yet."
            ),
            "receipts": [],
        }

    messages = [
        {
            "to": t.expo_push_token,
            "title": "Kolably test notification",
            "body": "If you can see this, push notifications are working.",
            "sound": "default",
            "priority": "high",
            "channelId": _ANDROID_CHANNEL_ID,
            "badge": 1,
            "data": {"type": "test_push"},
        }
        for t in tokens
    ]

    receipts = await _post(messages)

    detailed = []
    for token, receipt in zip((t.expo_push_token for t in tokens), receipts):
        status_value = receipt.get("status")
        detailed.append(
            {
                # Truncated: enough to tell two devices apart in the UI without
                # putting a full push credential on screen.
                "token": f"{token[:24]}…",
                "status": status_value,
                "error": receipt.get("details", {}).get("error") if status_value == "error" else None,
                "message": receipt.get("message") if status_value == "error" else None,
            }
        )
        if status_value == "error" and receipt.get("details", {}).get("error") == "DeviceNotRegistered":
            await repo.delete_by_token(token)

    accepted = sum(1 for r in detailed if r["status"] == "ok")
    return {
        "sent": accepted > 0,
        "devices": len(tokens),
        "detail": (
            f"Expo accepted the message for {accepted} of {len(tokens)} device(s). "
            "Acceptance only means Expo queued it — if nothing arrives, the problem is "
            "downstream (APNs/FCM credentials, notification permission, or Do Not Disturb)."
        ),
        "receipts": detailed,
    }


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
