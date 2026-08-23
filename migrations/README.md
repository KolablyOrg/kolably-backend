# Database Migrations

This directory contains all database migrations for the Kolably backend, organized as timestamped SQL files following the Supabase CLI convention.

## File Naming Convention

```
YYYYMMDDHHMMSS_description.sql
```

Example: `20260726150000_extensions_and_utility_functions.sql`

## Applying Migrations

### Option 1: Supabase Dashboard (Manual)

1. Go to your Supabase project → SQL Editor
2. Copy the contents of each migration file in chronological order
3. Run them one by one, starting from the oldest timestamp

### Option 2: Supabase CLI (Recommended)

If you have the [Supabase CLI](https://supabase.com/docs/guides/cli) installed:

```bash
# Login to Supabase
supabase login

# Link your project
supabase link --project-ref YOUR_PROJECT_REF

# Apply all pending migrations
supabase db push
```

The CLI will track which migrations have been applied and only run new ones.

### Option 3: psql (Direct)

```bash
# Connect to your Supabase database
psql "postgresql://postgres:[PASSWORD]@[HOST]:5432/postgres"

# Run migrations in order
\i migrations/20260726150000_extensions_and_utility_functions.sql
\i migrations/20260726150100_alter_profiles.sql
# ... etc
```

## Migration Order

All migrations are designed to be run in chronological order (by timestamp). Each migration is idempotent where possible (uses `IF NOT EXISTS`, `IF EXISTS` checks).

## Schema Documentation

The complete target schema is documented in:
- [`docs/schema.sql`](../docs/schema.sql) - Full DDL with comments
- [`docs/DB_DESIGN.md`](../docs/DB_DESIGN.md) - Design decisions and rationale
- [`docs/API_REQUIREMENTS.md`](../docs/API_REQUIREMENTS.md) - API contracts that drive schema

## Creating New Migrations

When making schema changes:

1. Create a new file with the next timestamp: `YYYYMMDDHHMMSS_your_change.sql`
2. Write your SQL changes
3. Test locally or on a Supabase branch first
4. Apply to production via Supabase Dashboard or CLI
5. Update `docs/schema.sql` if it's a significant change

## Migration History

| Migration | Description |
|-----------|-------------|
| 001 | Enable pg_trgm extension and create updated_at trigger function |
| 002 | Alter profiles: role TEXT+CHECK, ON DELETE CASCADE, updated_at trigger |
| 003 | Alter creators: add Instagram OAuth fields, social handles, indexes |
| 004 | Alter businesses: add logo_url, industry, is_verified, updated_at |
| 005 | Alter campaigns: add updated_at, FK CASCADE, trigram index |
| 006 | Alter campaign_applications: add updated_at, UNIQUE constraint, indexes |
| 007 | Create portfolio_items table |
| 008 | Create saved_campaigns table |
| 009 | Create collaborations table |
| 010 | Create content_submissions table |
| 011 | Create conversations and conversation_participants tables |
| 012 | Create messages table |
| 013 | Create conversation_reads table |
| 014 | Create notifications table |
| 015 | Auth user trigger for auto profile creation |
| 016 | Enable RLS on new tables and revoke public EXECUTE on functions |
| 017 | Alter creators: add website + following_count (Instagram pre-fill fields) |
| 018 | Create data_deletion_requests table (Meta Data Deletion Callback log) |
| 019 | Alter portfolio_items: add title column |
| 020 | Alter businesses: business_name nullable, add legal_entity_name/business_type/pan_number/gst_number/business_proof_document_url + kyb_status lifecycle (business signup + KYB verification) |
| 021 | Alter businesses: add kyb_rejection_reason (admin approve/reject KYB) |
| 022 | Add durable collaboration revision history and server-side revision-round counter |
| 023 | Synchronize direct payment confirmation with invoice status and record audit actors |
| 024 | Add collaboration lifecycle notification types for submission, approval, and verification |
| 025 | Create business_shortlists for persisted creator tags, notes, and comparison |
| 026 | Add view_count to portfolio_items (Instagram video insights) |
| 027 | Add views_count to creators (real aggregate for Engagement "Total views") |
| 028 | Chat Realtime: broadcast-on-insert trigger + participant RLS on realtime.messages |
| 029 | Notifications Realtime: broadcast-on-insert trigger + owner RLS on realtime.messages |

## Notes

- All migrations use `IF NOT EXISTS` / `IF EXISTS` where possible for idempotency
- Foreign keys use explicit `ON DELETE` behavior (CASCADE or SET NULL)
- Money is stored as `NUMERIC`, never `FLOAT`
- Enums are modeled as `TEXT + CHECK` constraints (not native Postgres ENUM) for easier evolution
- `updated_at` is maintained by trigger, not application code
- RLS is enabled on all tables; the backend uses Supabase service-role client (bypasses RLS)
