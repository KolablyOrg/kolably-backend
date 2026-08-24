# Integration tests

Real FastAPI routes → real services → real repositories → a **real local
Postgres + Supabase Auth instance** — the layer `tests/` deliberately skips
(there, Supabase and the repositories are faked). This is what actually
proves a migration, an RLS policy, or a repository's query is correct.

These tests are hermetic: they run against a throwaway local Supabase
instance started by the Supabase CLI, never against the real project in
`.env`. `conftest.py` refuses to run (`pytest.exit`) if `SUPABASE_URL`
doesn't look local, specifically to prevent an accidental run against real
data.

## Running locally

```bash
# One-time
brew install supabase/tap/supabase   # or: npm install -g supabase

cd kolably_backend
supabase start          # spins up local Postgres + GoTrue + Storage in Docker,
                         # applies migrations/ automatically (symlinked at
                         # supabase/migrations)

# Export the local instance's URL/keys as the app's env vars
eval "$(supabase status -o env | sed 's/"//g; s/^API_URL/SUPABASE_URL/; s/^ANON_KEY/SUPABASE_KEY/; s/^SERVICE_ROLE_KEY/SUPABASE_SERVICE_ROLE_KEY/; s/^JWT_SECRET/SUPABASE_JWT_SECRET/' | sed 's/^/export /')"

pip install -e ".[dev]"
pytest tests_integration/ -v

supabase stop            # tear down when done
```

`supabase start` needs Docker running.

## Why not `tests/`

Plain `pytest` (no args) only picks up `tests/` (see `testpaths` in
`pyproject.toml`), so this folder is opt-in and never runs by accident
without a local Supabase instance up. CI (`.github/workflows/deploy.yml`)
runs both suites separately as part of the pre-deploy gate.

## Adding a test

- Prefer exercising a full user-facing flow through the HTTP layer
  (`client.post(...)`) over calling services/repositories directly — that's
  what proves the wiring between them, not just the DB layer in isolation.
- Use `unique_email(...)` from `conftest.py` for anything that signs up a
  user — tests don't share accounts and there's no DB reset between runs.
- If a flow needs a real third-party integration (Instagram OAuth, Google,
  Razorpay), bypass it by writing the expected DB state directly via the
  relevant repository (see `test_campaign_collaboration_flow.py`'s
  Instagram-connected bypass) rather than trying to fake the external call.
