-- Migration: brand subscription / plan state
-- Description: businesses had no plan, tier, or billing state of any kind
-- (verified: no plan/tier/subscription column, and the only payment
-- reference anywhere in the codebase was two unused Razorpay keys in
-- config.py). This adds the state a subscription feature needs, WITHOUT
-- committing to a payment gateway — that decision is still open (Razorpay
-- vs Stripe) and is blocked on a live gateway account existing.
--
-- Gateway-agnostic on purpose:
--   * `billing_provider` records WHICH gateway a row belongs to, so a later
--     switch (or running both during a migration) doesn't need a schema
--     change and doesn't silently reinterpret old ids.
--   * `billing_customer_id` / `billing_subscription_id` are opaque TEXT.
--     Razorpay (`cust_...`/`sub_...`) and Stripe (`cus_...`/`sub_...`) both
--     fit; so would a manual/invoiced enterprise deal.
-- Nothing here parses or validates those ids — that belongs in the adapter.
--
-- Deliberately NOT included: prices, currencies, or quota numbers. Those
-- live in app/core/plans.py where they can be changed without a migration.
-- Putting a price in the database would freeze it into every existing row.
--
-- HOW THIS IS USED TODAY (2026-08-29): there is no payment gateway — one
-- requires GST registration, which isn't in place. Payment is taken
-- offline and a superadmin activates the subscription via
-- PATCH /businesses/{id}/plan, which writes billing_provider='manual'.
-- The gateway-shaped columns are populated by that path today and by an
-- adapter later, with no schema change needed either way.
-- Applied: 2026-08-29

ALTER TABLE businesses
  ADD COLUMN IF NOT EXISTS plan TEXT NOT NULL DEFAULT 'free',
  ADD COLUMN IF NOT EXISTS subscription_status TEXT NOT NULL DEFAULT 'none',
  ADD COLUMN IF NOT EXISTS billing_provider TEXT,
  ADD COLUMN IF NOT EXISTS billing_customer_id TEXT,
  ADD COLUMN IF NOT EXISTS billing_subscription_id TEXT,
  ADD COLUMN IF NOT EXISTS current_period_end TIMESTAMPTZ,
  -- When a paid plan was cancelled but paid through to period end. Kept
  -- separate from subscription_status so "cancelling" and "still entitled
  -- until the 30th" are both representable at once.
  ADD COLUMN IF NOT EXISTS cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE;

-- Existing businesses default to 'free'/'none', which is accurate: nobody
-- has ever been charged, so no backfill is needed or honest.

ALTER TABLE businesses
  DROP CONSTRAINT IF EXISTS businesses_plan_check;
ALTER TABLE businesses
  ADD CONSTRAINT businesses_plan_check
  CHECK (plan = ANY (ARRAY['free'::text, 'pro'::text]));

-- Mirrors the states every major gateway exposes, so webhook handling can
-- map onto it without inventing a translation layer:
--   none      — never subscribed (the default for a free account)
--   trialing  — in a trial period, entitled
--   active    — paid and entitled
--   past_due  — payment failed, still entitled during the retry window
--   canceled  — no longer entitled
ALTER TABLE businesses
  DROP CONSTRAINT IF EXISTS businesses_subscription_status_check;
ALTER TABLE businesses
  ADD CONSTRAINT businesses_subscription_status_check
  CHECK (subscription_status = ANY (ARRAY[
    'none'::text, 'trialing'::text, 'active'::text, 'past_due'::text, 'canceled'::text
  ]));

ALTER TABLE businesses
  DROP CONSTRAINT IF EXISTS businesses_billing_provider_check;
ALTER TABLE businesses
  ADD CONSTRAINT businesses_billing_provider_check
  CHECK (billing_provider IS NULL OR billing_provider = ANY (ARRAY[
    'razorpay'::text, 'stripe'::text, 'manual'::text
  ]));

-- Webhooks arrive keyed by the gateway's subscription id, not our business
-- id, so that lookup has to be fast and unambiguous. Partial + UNIQUE:
-- many rows are legitimately NULL (every free account), but a given
-- gateway subscription must never map to two businesses.
CREATE UNIQUE INDEX IF NOT EXISTS idx_businesses_billing_subscription_id
    ON businesses (billing_subscription_id)
 WHERE billing_subscription_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_businesses_billing_customer_id
    ON businesses (billing_customer_id)
 WHERE billing_customer_id IS NOT NULL;

COMMENT ON COLUMN businesses.plan IS
  'Entitlement tier: free (3 campaigns/month) or pro (unlimited campaigns). Quotas live in app/core/plans.py, NOT here, so they can change without a migration.';
COMMENT ON COLUMN businesses.current_period_end IS
  'When entitlement lapses. For manually-activated subscriptions this is the safety net — a human grants access and may forget to revoke it, so an expiry makes it lapse on its own (see plans.resolve_plan). NULL means open-ended and must be switched off by hand.';
COMMENT ON COLUMN businesses.subscription_status IS
  'Billing lifecycle state, mirroring the states Razorpay/Stripe both expose. Entitlement is derived from plan + status together (see plans.resolve_plan) — status alone is not enough, since a past_due account is still entitled during the retry window.';
COMMENT ON COLUMN businesses.billing_provider IS
  'Which gateway billing_customer_id/billing_subscription_id belong to. NULL for accounts that never subscribed. Recorded explicitly so a future gateway change cannot silently reinterpret existing ids.';
