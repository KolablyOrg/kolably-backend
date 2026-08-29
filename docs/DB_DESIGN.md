# Kolably MVP — DB Design Notes

Companion to `schema.sql`. Read that file top-to-bottom first — the comments
inline explain most decisions. This file covers the *why* behind the trickier
calls and flags things that need a decision before/while building.

## 1. Identity model

`profiles` is the one true identity table (1:1 with `auth.users`), and
`creators`/`businesses` hang off it via `profile_id`. This matches what
`auth_service.py` already does (`GET /auth/me` returns profile + role-specific
data) and avoids resurrecting the dead `users` table PROJECT_STATUS.md flags
for deletion.

The `on_auth_user_created` trigger only inserts into `profiles` — it does
**not** create `creators`/`businesses` rows, since which one to create
depends on which signup endpoint was hit (`/auth/signup/creator` vs.
`/auth/signup/business`), which the trigger can't know. `auth_service`
inserts that row explicitly, same as today.

## 2. Enum modeling: TEXT + CHECK, not native `ENUM`

Every status/type column is `TEXT` with a `CHECK` constraint, mirroring the
Python `str, Enum` classes in `API_REQUIREMENTS.md` §"New enums". Reasons:
- Adding a new value is `DROP CONSTRAINT` / `ADD CONSTRAINT` — no `ALTER
  TYPE ... ADD VALUE` transaction-boundary headaches.
- Values serialize identically to the Pydantic enum's `.value`, so no
  translation layer at the ORM boundary.
- Matches the pattern the codebase already uses for `campaigns.status`.

## 3. Resolves the existing schema drift (PROJECT_STATUS.md)

- Column names follow the **code's** naming, not the stale
  `app/docs/db_schema.md`: `location` (not `city`), `status` (not
  `campaign_status`), `cash_amount_min/max` (not `cash_payment`),
  `follower_range_min/max` (not `min_followers`/`max_followers`),
  `free_product_description` (not `free_product`).
- Adds the columns `campaign_service.py` reads/writes but that were missing
  from both `db_schema.md` and `migrate_campaigns.sql`: `direction`,
  `instagram_handle`, `example_content_url`, `revision_reason` on
  `campaign_applications`. This schema is the reconciliation point — once
  applied, `app/docs/db_schema.md` should be regenerated from it, not
  hand-maintained separately.

## 4. Collaborations link back to the originating application

`collaborations.application_id` (unique, nullable via `ON DELETE SET NULL`)
wasn't explicitly requested but costs nothing and answers "which
application/invite led to this collaboration" without a join through
`campaign_id + creator_id` (which isn't reliably unique once a creator can
reapply after rejection in a later iteration).

## 5. Chat: two tables, not one denormalized thread

`conversations` + `conversation_participants` (rather than a fixed
`participant_a`/`participant_b` pair on `conversations`) so a future group
chat or a support/staff participant doesn't require a schema change — only
`ConversationResponse.participant_ids` needs no change at all, it already
reads as a list.

**Open item:** the get-or-create uniqueness for `collaboration_id IS NULL`
conversations (two people messaging with no collaboration context) isn't
enforceable as a plain DB constraint — Postgres can't index "this pair of
rows in a child table is unique" directly. For MVP, every real conversation
*does* have a `collaboration_id` (chat only spins up after an accepted
application per the build order), so this is schema-ready but not yet
load-bearing. If direct messaging without a collaboration ships later,
either add a sorted-pair hash column on `conversations` or enforce it in
`chat_service` with a `SELECT ... FOR UPDATE`-guarded get-or-create.

## 6. What's deliberately *not* in this schema

- **No Razorpay/payment tables.** MVP explicitly has no payment processing
  (API_REQUIREMENTS.md §MVP scope, point 1) — nothing to model yet.
- **No affiliate-tracking tables.** `collaborations.affiliate_url` is a
  placeholder column; the generation/tracking logic is an explicit TODO in
  `collaboration_service.py`, not an MVP requirement.
- **No YouTube/TikTok integration tables.** Those platforms stay
  self-reported (`content_submissions.views/likes/comments` entered by hand)
  — no token/sync columns needed for them, unlike Instagram.
- **No `users` table.** Recommend dropping the dead stub module entirely
  rather than giving it a table, per PROJECT_STATUS.md's own suggestion.

## 7. Storage buckets (Supabase Storage, not Postgres tables)

Referenced by `*_url` columns above but live outside Postgres. A single
public S3 bucket — `media` — holds everything, namespaced by top-level
folder per purpose (`avatar/`, `business-logo/`, `campaign-cover/`,
`campaign-reference/`, `verification-doc/`). The backend talks to it over Supabase's S3-compatible
endpoint via `app/services/storage_service.py` (boto3) using the S3 access
keys, and hands back public URLs of the form
`{SUPABASE_URL}/storage/v1/object/public/media/{key}`.

Not part of `schema.sql`; tracked here so it isn't lost. The bucket is
created once in the Supabase dashboard (Storage → new bucket), not via a
migration — Supabase offers no Postgres DDL for bucket creation.

## 8. Suggested migration path from the live DB

The live DB already has `migrate_campaigns.sql` applied. To get from "live
today" to this schema:

1. `profiles`/`creators`/`businesses`/`campaigns`/`campaign_applications`
   already exist — reconcile column names/types against §3 above (rename
   don't recreate, to preserve data).
2. Add the net-new tables wholesale: `portfolio_items` (if not already
   present), `saved_campaigns`, `collaborations`, `content_submissions`,
   `conversations`, `conversation_participants`, `messages`,
   `conversation_reads`, `notifications`.
3. Add the missing `campaign_applications` columns called out in §3.
4. Backfill `campaign_applications.direction = 'creator_applied'` for
   existing rows (already the column default, but be explicit in the
   migration for auditability).

`schema.sql` is written with `IF NOT EXISTS` throughout so it's safe to run
directly against the live DB for the net-new pieces; the renames in step 1
are the one part that needs a hand-written `ALTER TABLE ... RENAME COLUMN`
migration rather than a fresh `CREATE TABLE`.
