# Testing Automation Plan (cross-repo)

parent:: [[context]]
source:: /Users/sky/Documents/Kolably/TESTING_AUTOMATION_PLAN.md
date:: 2026-08-23
saved-because:: Defines the testing/CI roadmap for both this repo and the sibling `kolably_ui` frontend repo; not derivable from this repo alone since it lives one directory up and spans two codebases.

## Summary
Plan scoped to `kolably_ui` (web) + `kolably_backend`, mobile app out of
scope for now. Status quo as verified against both repos on 2026-08-23:

- **Backend unit tests**: `tests/` (~20 files) test services against fake/mocked
  repositories — no test ever talks to a real Supabase/Postgres instance, so
  RLS policies and real SQL behavior are untested.
- **Backend CI**: `.github/workflows/deploy.yml` runs `ruff` + `pytest` before
  every EC2 deploy — unit-level only, no post-deploy smoke check.
- **Frontend unit tests**: thin Vitest coverage, not CI-gated.
- **Frontend e2e**: Playwright configured with ~20 specs, but they're
  exploratory/manual (`scratch-*`, `qa-*`) rather than a maintained suite, and
  `kolably_ui` has zero GitHub Actions workflows.
- **No staging environment** and **no scheduled/synthetic uptime checks** exist
  for either repo.

The plan proposes (in phases): real Supabase-backed backend integration tests
(via local ephemeral Supabase in CI), a staging environment (second Supabase
project/branch + second Docker container on the same EC2 box + Vercel preview
domain), post-deploy smoke tests, and a nightly scheduled regression suite —
all using free/OSS tooling (Playwright, pytest, GitHub Actions), no paid SaaS.
Visual regression, load testing, and dependency scanning are explicitly
deferred to post-launch.

## Relevance to this project
Directly affects this repo's `tests/` directory and `.github/workflows/`: any
new integration-test setup would need local-Supabase bootstrapping in CI
against `migrations/`, and any staging deploy would reuse the same
Docker/nginx pattern documented in `docs/DEPLOYMENT.md`.

## Used in
- [[logs/2026-08-23]]
