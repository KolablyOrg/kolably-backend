-- Migration: 000 - Baseline schema (create-from-scratch bootstrap)
-- Description: Every table every later migration in this directory assumes
-- already exists (profiles, creators, businesses, campaigns, ...). Without
-- this file, replaying migrations/ against a genuinely fresh database fails
-- immediately — 20260726150100_alter_profiles.sql ALTERs a `profiles` table
-- that nothing before it ever created. Production and every existing
-- Supabase project were bootstrapped by hand from docs/schema.sql (see that
-- file's own header: "this is the CLEAN, FULL definition"), so this gap
-- only ever showed up when trying to spin up a brand-new instance —
-- confirmed by running `supabase start` against an empty local Postgres.
--
-- This file was docs/schema.sql verbatim at the time it was written, given
-- the earliest possible timestamp so the Supabase CLI (and any other tool
-- that just runs migrations/*.sql in order) applies it first. Like every
-- other file in this directory, treat it as immutable once merged — future
-- schema changes (including any more drift discovered between docs/
-- schema.sql and the real database) belong in new, later-timestamped
-- migration files, not edits here.
--
-- Verified: docs/schema.sql followed by every existing migration file, in
-- timestamp order, applies cleanly to an empty database with zero errors
-- (docs/schema.sql itself already lags a few recent migrations — e.g.
-- business_shortlists, kyb fields, view/views_count columns — which are
-- exactly what the later migration files in this directory then add).
-- Applied: 2026-08-23

-- Kolably — Complete MVP Database Design
-- ════════════════════════════════════════════════════════════════════════
-- Target schema derived from API_REQUIREMENTS.md (all 8 domains) + the
-- existing campaigns/campaign_applications reality (migrate_campaigns.sql,
-- PROJECT_STATUS.md drift notes). This is the CLEAN, FULL definition —
-- treat it as the source of truth going forward, not an incremental patch.
--
-- Design principles:
--   1. `profiles` is the single identity table (1:1 with Supabase auth.users).
--      `creators` / `businesses` are role-specific extensions, not separate
--      identities — this avoids the auth/users duplication already flagged
--      as dead code in PROJECT_STATUS.md.
--   2. Enums are modeled as TEXT + CHECK constraints (not native Postgres
--      ENUM types), because the app already treats them as Python
--      `str, Enum` — TEXT+CHECK is trivial to extend (ADD/DROP CONSTRAINT)
--      without the ALTER TYPE ceremony native enums require. This matches
--      the pattern already used for campaigns.status.
--   3. Every FK has an explicit ON DELETE behavior — no implicit RESTRICT
--      surprises.
--   4. `updated_at` is maintained by trigger, not by application code.
--   5. Money is NUMERIC, never FLOAT.
--   6. Naming matches the *code's* naming (per PROJECT_STATUS §Schema
--      drift), not the older app/docs/db_schema.md — e.g.
--      follower_range_min/max, cash_amount_min/max, location, status.
-- ════════════════════════════════════════════════════════════════════════

create extension if not exists pgcrypto;   -- gen_random_uuid()

-- Reusable updated_at trigger
create or replace function set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ────────────────────────────────────────────────────────────────────────
-- 0. IDENTITY — profiles (1:1 with auth.users)
-- ────────────────────────────────────────────────────────────────────────
create table if not exists profiles (
  id           uuid primary key default gen_random_uuid(),
  auth_id      uuid not null unique references auth.users(id) on delete cascade,
  email        text not null unique,
  role         text not null default 'creator'
               check (role in ('creator', 'business', 'superadmin')),
  is_active    boolean not null default true,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
drop trigger if exists trg_profiles_updated_at on profiles;
create trigger trg_profiles_updated_at
  before update on profiles
  for each row execute function set_updated_at();

-- Auto-create a profiles row whenever a Supabase auth user is created.
-- `role` and `email` are supplied via signup metadata; creators/businesses
-- rows are inserted explicitly by auth_service, not by this trigger.
create or replace function handle_new_auth_user()
returns trigger language plpgsql security definer as $$
begin
  insert into public.profiles (auth_id, email, role)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data->>'role', 'creator')
  );
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function handle_new_auth_user();

-- ────────────────────────────────────────────────────────────────────────
-- 1. CREATORS
-- ────────────────────────────────────────────────────────────────────────
create table if not exists creators (
  id                            uuid primary key default gen_random_uuid(),
  profile_id                    uuid not null unique references profiles(id) on delete cascade,

  name                          text not null,
  bio                           text,
  niche                         text,              -- matches campaigns.creator_category
  city                          text,
  profile_photo_url             text,              -- Supabase Storage `avatars`, pre-Instagram fallback

  follower_count                int default 0,
  engagement_rate               numeric,

  -- Self-reported handles (not integrated)
  youtube_handle                text,
  tiktok_handle                 text,

  -- Instagram connection (Meta Graph API) — internal only, never serialized
  instagram_handle              text,
  instagram_user_id             text,
  instagram_access_token        text,               -- encrypted at rest (app-layer)
  instagram_token_expires_at    timestamptz,
  instagram_synced_at           timestamptz,

  created_at                    timestamptz not null default now(),
  updated_at                    timestamptz not null default now()
);
create index if not exists idx_creators_niche on creators(niche);
create index if not exists idx_creators_city on creators(city);
create index if not exists idx_creators_follower_count on creators(follower_count);

drop trigger if exists trg_creators_updated_at on creators;
create trigger trg_creators_updated_at
  before update on creators
  for each row execute function set_updated_at();

create table if not exists portfolio_items (
  id              uuid primary key default gen_random_uuid(),
  creator_id      uuid not null references creators(id) on delete cascade,
  title           text,                              -- optional label for manual additions
  media_url       text not null,                    -- Storage `portfolio`, or IG media URL
  post_link       text,                              -- IG permalink, if imported
  media_type      text not null default 'photo' check (media_type in ('photo', 'video')),
  like_count      int,
  comment_count   int,
  created_at      timestamptz not null default now()
);
create index if not exists idx_portfolio_items_creator_id on portfolio_items(creator_id);
create index if not exists idx_portfolio_items_media_type on portfolio_items(media_type);

-- ────────────────────────────────────────────────────────────────────────
-- 2. BUSINESSES
-- ────────────────────────────────────────────────────────────────────────
create table if not exists businesses (
  id             uuid primary key default gen_random_uuid(),
  profile_id     uuid not null unique references profiles(id) on delete cascade,

  business_name  text not null,
  logo_url       text,                              -- Supabase Storage `avatars`
  industry       text,
  website        text,
  description    text,
  is_verified    boolean not null default false,    -- manual, superadmin-only

  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);
create index if not exists idx_businesses_is_verified on businesses(is_verified);

drop trigger if exists trg_businesses_updated_at on businesses;
create trigger trg_businesses_updated_at
  before update on businesses
  for each row execute function set_updated_at();

-- ────────────────────────────────────────────────────────────────────────
-- 3. CAMPAIGNS
-- ────────────────────────────────────────────────────────────────────────
create table if not exists campaigns (
  id                          uuid primary key default gen_random_uuid(),
  business_id                 uuid not null references businesses(id) on delete cascade,

  -- Step 1: foundations
  title                       text not null,
  objective                   text not null check (objective in (
                                'brand_awareness', 'product_launch', 'foot_traffic',
                                'user_generated_content', 'sales_conversion',
                                'event_promotion', 'engagement', 'other'
                              )),
  description                 text,

  -- Brief / objective & audience (4-step wizard)
  platforms                   jsonb not null default '[]',
  product_promoted            text,
  audience_age_range          text,
  audience_gender             text,
  audience_location           text,
  audience_interests          text,
  key_messaging               text,
  dos                         text,
  donts                       text,
  reference_image_urls        jsonb not null default '[]',
  content_due_at              timestamptz,

  -- Step 2: deliverables & offer
  deliverables                jsonb not null default '[]',   -- [{platform, content_type, quantity, description, required}]
  compensation_type           text check (compensation_type in ('cash', 'product', 'cash_and_product')),
  cash_amount_min             numeric,
  cash_amount_max             numeric,
  free_product_description    text,

  -- Step 3: targeting
  creator_category            text,              -- matched against creators.niche
  follower_range_min          int,
  follower_range_max          int,
  min_engagement_rate         numeric,
  location                    text,
  max_creators                int,
  additional_requirements     text,

  -- Step 4: publish
  cover_image_url             text,              -- Supabase Storage `campaign-covers`
  deadline                    timestamptz,

  status                      text not null default 'draft'
                               check (status in ('draft', 'active', 'closed', 'completed')),

  created_at                  timestamptz not null default now(),
  updated_at                  timestamptz not null default now()
);
create index if not exists idx_campaigns_business_id on campaigns(business_id);
create index if not exists idx_campaigns_status on campaigns(status);
create index if not exists idx_campaigns_creator_category on campaigns(creator_category);
create index if not exists idx_campaigns_location on campaigns(location);
create index if not exists idx_campaigns_created_at on campaigns(created_at desc);
-- Full-text-ish search on title/description; upgrade to tsvector if search
-- volume ever demands it — trigram is enough for MVP `search` param.
create extension if not exists pg_trgm;
create index if not exists idx_campaigns_title_trgm on campaigns using gin (title gin_trgm_ops);

drop trigger if exists trg_campaigns_updated_at on campaigns;
create trigger trg_campaigns_updated_at
  before update on campaigns
  for each row execute function set_updated_at();

create table if not exists saved_campaigns (
  creator_id   uuid not null references creators(id) on delete cascade,
  campaign_id  uuid not null references campaigns(id) on delete cascade,
  created_at   timestamptz not null default now(),
  primary key (creator_id, campaign_id)
);

-- ────────────────────────────────────────────────────────────────────────
-- 4. APPLICATIONS (table name kept as campaign_applications — existing code
--    already queries this name; API domain is /api/v1/applications)
-- ────────────────────────────────────────────────────────────────────────
create table if not exists campaign_applications (
  id                     uuid primary key default gen_random_uuid(),
  campaign_id            uuid not null references campaigns(id) on delete cascade,
  creator_id             uuid not null references creators(id) on delete cascade,

  direction              text not null default 'creator_applied'
                         check (direction in ('creator_applied', 'business_invited')),
  message                text,
  instagram_handle       text,             -- snapshot at time of application
  example_content_url    text,

  status                 text not null default 'pending'
                         check (status in ('pending', 'accepted', 'rejected', 'revision_requested')),
  revision_reason        text,

  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now(),

  -- one application/invite per creator per campaign — backs the 409-on-
  -- duplicate-invite requirement and prevents duplicate creator applies
  unique (campaign_id, creator_id)
);
create index if not exists idx_campaign_applications_campaign_id on campaign_applications(campaign_id);
create index if not exists idx_campaign_applications_creator_id on campaign_applications(creator_id);
create index if not exists idx_campaign_applications_status on campaign_applications(status);

drop trigger if exists trg_campaign_applications_updated_at on campaign_applications;
create trigger trg_campaign_applications_updated_at
  before update on campaign_applications
  for each row execute function set_updated_at();

-- ────────────────────────────────────────────────────────────────────────
-- 5. COLLABORATIONS & CONTENT SUBMISSIONS
-- ────────────────────────────────────────────────────────────────────────
create table if not exists collaborations (
  id               uuid primary key default gen_random_uuid(),
  -- traceability back to the accepted application (either direction)
  application_id   uuid unique references campaign_applications(id) on delete set null,
  campaign_id      uuid not null references campaigns(id) on delete cascade,
  creator_id       uuid not null references creators(id) on delete cascade,
  business_id      uuid not null references businesses(id) on delete cascade,

  status           text not null default 'active'
                   check (status in ('active', 'content_submitted', 'revision_requested', 'approved', 'live_submitted', 'completed', 'cancelled')),
  affiliate_url    text,       -- reserved: affiliate tracking is planned, not built (see collaboration_service TODO)
  revision_rounds  integer not null default 0 check (revision_rounds >= 0),

  created_at       timestamptz not null default now(),
  completed_at     timestamptz
);
create index if not exists idx_collaborations_creator_id on collaborations(creator_id);
create index if not exists idx_collaborations_business_id on collaborations(business_id);
create index if not exists idx_collaborations_campaign_id on collaborations(campaign_id);
create index if not exists idx_collaborations_status on collaborations(status);

create table if not exists collaboration_revision_history (
  id               uuid primary key default gen_random_uuid(),
  collaboration_id uuid not null references collaborations(id) on delete cascade,
  revision_number  integer not null check (revision_number > 0),
  requested_by     uuid not null references profiles(id) on delete restrict,
  notes            jsonb not null default '[]',
  overall_note     text,
  created_at       timestamptz not null default now(),
  unique (collaboration_id, revision_number)
);
create index if not exists idx_collab_revision_history_collaboration
  on collaboration_revision_history(collaboration_id, created_at desc);

create table if not exists content_submissions (
  id                uuid primary key default gen_random_uuid(),
  collaboration_id  uuid not null references collaborations(id) on delete cascade,
  content_url       text not null,
  platform          text not null check (platform in ('instagram', 'youtube', 'tiktok')),

  -- instagram: fetched via Graph API; other platforms: self-reported
  views             int,
  likes             int,
  comments          int,
  notes             text,
  synced_at         timestamptz,     -- last Graph API refresh (instagram only)

  submitted_at      timestamptz not null default now()
);
create index if not exists idx_content_submissions_collaboration_id on content_submissions(collaboration_id);
create index if not exists idx_content_submissions_platform on content_submissions(platform);

-- ────────────────────────────────────────────────────────────────────────
-- 6. CHAT
-- ────────────────────────────────────────────────────────────────────────
create table if not exists conversations (
  id                uuid primary key default gen_random_uuid(),
  -- nullable: chat can exist independent of a collaboration in future,
  -- but MVP only creates one from an accepted application/collaboration
  collaboration_id  uuid references collaborations(id) on delete set null,
  created_at        timestamptz not null default now()
);
-- enforces "one conversation per collaboration" for the get-or-create flow
create unique index if not exists uq_conversations_collaboration_id
  on conversations(collaboration_id) where collaboration_id is not null;

create table if not exists conversation_participants (
  conversation_id  uuid not null references conversations(id) on delete cascade,
  profile_id       uuid not null references profiles(id) on delete cascade,
  primary key (conversation_id, profile_id)
);
create index if not exists idx_conversation_participants_profile_id on conversation_participants(profile_id);
-- Note: for collaboration_id IS NULL conversations (not used in MVP but
-- schema-ready), get-or-create must look up existing rows via a join on
-- conversation_participants for the given pair rather than a DB constraint,
-- since uniqueness of an unordered pair isn't a plain index in Postgres.

create table if not exists messages (
  id               uuid primary key default gen_random_uuid(),
  conversation_id  uuid not null references conversations(id) on delete cascade,
  sender_id        uuid not null references profiles(id) on delete cascade,
  content          text not null,
  created_at       timestamptz not null default now(),
  -- 'text' = typed; 'event' = campaign-lifecycle system row
  kind             text not null default 'text',
  metadata         jsonb
);
create index if not exists idx_messages_conversation_id_created_at on messages(conversation_id, created_at);

-- Realtime: AFTER INSERT broadcasts to private topic conversation:{id}.
-- Participants join via RLS on realtime.messages, joining
-- conversation_participants.profile_id -> profiles.id where
-- profiles.auth_id = auth.uid(). See 20260822100000_chat_realtime_broadcast.sql.

create table if not exists conversation_reads (
  conversation_id  uuid not null references conversations(id) on delete cascade,
  profile_id       uuid not null references profiles(id) on delete cascade,
  last_read_at     timestamptz not null default now(),
  primary key (conversation_id, profile_id)
);

-- ────────────────────────────────────────────────────────────────────────
-- 7. NOTIFICATIONS
-- ────────────────────────────────────────────────────────────────────────
create table if not exists notifications (
  id           uuid primary key default gen_random_uuid(),
  profile_id   uuid not null references profiles(id) on delete cascade,
  type         text not null check (type in (
                 'application_received', 'application_accepted', 'application_rejected',
                 'revision_requested', 'application_resubmitted', 'campaign_invite_received',
                 'new_message', 'collaboration_completed', 'invoice_received',
                 'collaboration_content_submitted', 'collaboration_draft_approved',
                 'collaboration_live_verified'
               )),
  title        text not null,
  body         text not null,
  related_id   uuid,          -- polymorphic reference (application/collaboration/conversation id) — app-resolved, no FK
  is_read      boolean not null default false,
  created_at   timestamptz not null default now()
);
create index if not exists idx_notifications_profile_unread on notifications(profile_id, is_read);
create index if not exists idx_notifications_created_at on notifications(created_at desc);

-- Realtime: AFTER INSERT broadcasts to private topic notifications:{profile_id}.
-- Only the owning profile can subscribe, via RLS on realtime.messages joining
-- profiles.id -> profiles.auth_id = auth.uid(). See
-- 20260823150000_notifications_realtime_broadcast.sql.

-- ────────────────────────────────────────────────────────────────────────
-- 8. GRANTS — a genuinely fresh Supabase project (self-hosted, CLI-managed,
--    or any cloud project created after Supabase's "auto_expose_new_tables"
--    default flipped off) does NOT expose newly created tables to
--    PostgREST's anon/authenticated/service_role roles automatically —
--    confirmed by running this schema against a truly empty local
--    instance, which failed with "permission denied for table profiles"
--    on the backend's own service-role client. The real Kolably project
--    has almost certainly never hit this because it was created before
--    that default changed and inherited the legacy auto-expose behavior,
--    so this gap only surfaces when bootstrapping anywhere new.
--
--    RLS (enabled on every table — see the RLS migrations) still governs
--    per-row access for anon/authenticated regardless of these grants;
--    service_role's queries all go through the backend's Python-enforced
--    authorization (see app/core/supabase.py), not RLS.
-- ────────────────────────────────────────────────────────────────────────
grant usage on schema public to anon, authenticated, service_role;

grant all on all tables in schema public to service_role;
grant all on all sequences in schema public to service_role;
grant all on all routines in schema public to service_role;
alter default privileges in schema public grant all on tables to service_role;
alter default privileges in schema public grant all on sequences to service_role;
alter default privileges in schema public grant all on routines to service_role;

grant select, insert, update, delete on all tables in schema public to authenticated;
grant usage, select on all sequences in schema public to authenticated;
alter default privileges in schema public grant select, insert, update, delete on tables to authenticated;
alter default privileges in schema public grant usage, select on sequences to authenticated;

grant select on all tables in schema public to anon;
alter default privileges in schema public grant select on tables to anon;

-- ════════════════════════════════════════════════════════════════════════
-- End of schema
-- ════════════════════════════════════════════════════════════════════════
