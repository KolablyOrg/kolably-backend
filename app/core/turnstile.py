"""
Cloudflare Turnstile verification — bot protection for signup.

Inert until `TURNSTILE_SECRET_KEY` is configured (see config.py's warning
about the mobile-app implication before setting it in production).
"""

import logging

import httpx

from app.core.config import settings
from app.core.exceptions import BadRequestError

logger = logging.getLogger(__name__)

_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def verify_turnstile(token: str | None, remote_ip: str | None) -> None:
    """Raises BadRequestError if verification fails. No-ops (soft pass) if
    the secret key isn't configured — see the module/config docstring."""
    if not settings.TURNSTILE_SECRET_KEY:
        return

    if not token:
        raise BadRequestError("Bot verification is required")

    payload = {"secret": settings.TURNSTILE_SECRET_KEY, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(_VERIFY_URL, data=payload)
            result = resp.json()
    except (httpx.HTTPError, ValueError):
        logger.exception("Turnstile verification request failed")
        raise BadRequestError("Bot verification failed — please try again") from None

    if not result.get("success"):
        logger.warning("Turnstile verification rejected: %s", result.get("error-codes"))
        raise BadRequestError("Bot verification failed — please try again")
