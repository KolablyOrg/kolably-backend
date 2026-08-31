# Brand subscriptions: the gateway-agnostic half is built, the gateway half is not

parent:: [[context]]
source:: implementing tracker item #2 (subscription model for brands)
date:: 2026-08-29
saved-because:: this feature is deliberately half-built, and the seam between the two halves is not obvious from the code alone. Anyone picking it up needs to know what exists, what is a placeholder, and what decision is still outstanding — otherwise the placeholder numbers get mistaken for a pricing decision.

## What was verified before building
All three claims in the user's tracker item checked out:
- `businesses` had **no** plan/tier/subscription column of any kind.
- Razorpay keys exist in `app/core/config.py` and `.env.example` but are
  referenced **nowhere else** — genuinely unused, confirmed by grep.
- Stripe has zero presence.

A **fourth** blocker the tracker didn't mention: the plans themselves are
undefined. The landing page (`src/components/landing/Pricing.tsx`) shows ₹0
on both cards and says "usage-based plans launching soon". No tier, price,
or quota exists anywhere in code or docs.

## What was built (usable now, no gateway needed)
- `migrations/20260829160000_add_business_subscription.sql` — `plan`,
  `subscription_status`, `billing_provider`, `billing_customer_id`,
  `billing_subscription_id`, `current_period_end`, `cancel_at_period_end`,
  with CHECK constraints and a partial UNIQUE index on
  `billing_subscription_id` (webhooks arrive keyed by that, not by our id).
- `app/core/plans.py` — tiers, quotas, and `resolve_plan()`.
- Campaign creation gated on the quota
  (`campaign_service._assert_campaign_quota_available`), returning **402**,
  not 403 — the caller isn't forbidden, they've hit a payment-shaped limit,
  and the client needs that distinction to show an upgrade prompt.
- Tests: `tests/test_plans.py` plus three gate tests in
  `test_campaign_service.py`.

## Design decisions worth not re-litigating
- **`billing_provider` is stored explicitly.** Without it, switching
  gateways later would silently reinterpret existing opaque ids. Costs one
  column; removes a whole class of migration bug.
- **Entitlement resolves from `plan` AND `subscription_status` together.**
  The `plan` column does not clean itself up — a cancellation webhook can
  update status and leave `plan='pro'` behind, and webhooks are exactly the
  kind of thing that arrives late or gets missed. Reading `plan` alone
  would grant unlimited access forever after a cancellation. There's a test
  for this.
- **`past_due` still grants access.** A failed card must not revoke a
  paying customer mid-campaign; gateways retry for days. Access ends at
  `canceled`.
- **Unknown plan/status values degrade to free, never raise.** Fail closed
  on privilege, never 500 an endpoint over an unrecognised string.
- **No prices or quotas in the database.** They live in `plans.py` so they
  can change without a migration. A price in a DB default would freeze a
  guess into every existing row.
- **The quota is on *concurrently held* campaigns, not campaigns per
  month.** That's a COUNT against current state — no usage table, no
  month-boundary reset logic. The landing copy ("free campaigns … monthly")
  leans toward a monthly allowance instead; **that is a different
  mechanism, not a tweak to this check**, and needs a usage-tracking table.
  Flagged in the function's own docstring too.
- Drafts count against the quota. Excluding them would let a business hold
  unlimited campaigns by never publishing.

## ⚠️ What is NOT decided, and must not be mistaken for decided
1. **Every number in `plans.py` is a placeholder** (free = 1 active
   campaign, 25 searches/month; pro = unlimited). These exist so the
   machinery could be built and tested. They are not a pricing proposal.
   The module docstring says so in a box; keep it there.
2. **The gateway is still undecided.** Razorpay is the natural fit (keys
   already present, product prices in ₹, India-first) but nothing has been
   committed and no adapter exists.
3. **Blocked on**: Aakash setting up the live gateway account. Without it
   there are no test keys, no webhook secret, and no way to verify an
   integration end-to-end.

## What remains (the gateway half)
- A payment adapter (create customer, create subscription, cancel).
- A webhook endpoint mapping gateway events onto `plan` /
  `subscription_status` / `current_period_end` / `cancel_at_period_end`.
  Must be idempotent and signature-verified.
- Brand billing UI on web + mobile.
- `max_creator_searches_per_month` is defined but **deliberately not
  enforced anywhere** — gating discovery changes behaviour for every
  existing user, which is a product call, not an implementation detail.

## Used in
- [[logs/2026-08-29]]
