"""
Rate limiting for abuse-prone endpoints (login, signup, password reset, 2FA
verification) — none of these had any throttling, leaving credential
stuffing / brute force / signup spam fully unmitigated.

Keyed by client IP. Kept as a single shared `Limiter` so every decorated
route reports to the same in-memory store.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
