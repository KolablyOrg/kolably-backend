"""
Billing gateway integration.

Split deliberately into two halves:

  base.py  — the contract every gateway must satisfy, plus the normalised
             event shape. Gateway-agnostic, complete, and testable today.
  <gateway>.py — ONE file implementing that contract. Does not exist yet:
             the gateway (Razorpay vs Stripe) is still undecided and is
             blocked on a live account existing.

Everything downstream of `SubscriptionEvent` — applying it to a business,
resolving entitlement, gating campaign creation — is already built and
tested against the normalised shape, so adding a gateway is genuinely one
new file plus one route registration, not a feature rewrite.
"""

from app.services.billing.base import (
    BillingGateway,
    SubscriptionEvent,
    SubscriptionEventType,
)

__all__ = ["BillingGateway", "SubscriptionEvent", "SubscriptionEventType"]
