# kolably_ui's e2e-regression CI job fails: missing BACKEND_REPO_TOKEN secret

parent:: [[context]]
source:: user pasted a CI error line; diagnosed root cause from the workflow file
date:: 2026-08-23
saved-because:: the visible error is a misleading downstream symptom, not the actual failure — anyone (including a future session) who sees the "No such file or directory" line and tries to fix *that* step will be chasing the wrong thing.

## Summary
`kolably_ui/.github/workflows/e2e-regression.yml` (added by commit
`bea7f98`, "Add CI: lint, unit tests, and a hermetic Playwright regression
suite") checks out `kolably-backend` as a sibling directory to run a
hermetic e2e suite (local Supabase + local backend + local frontend). That
checkout step requires a **fine-grained PAT stored as the
`BACKEND_REPO_TOKEN` secret** in `kolably_ui`'s GitHub repo settings — the
workflow's own comment says so explicitly — because the default
`GITHUB_TOKEN` can't read a sibling private repo.

Without that secret configured, the "Checkout kolably-backend" step fails,
so the `kolably_backend/` directory never gets created. Every subsequent
step that does `working-directory: kolably_backend` then fails too — but
the error a user actually sees is usually the **last** one,
`supabase stop --no-backup` (marked `if: always()`, so it runs even after
earlier failures), producing a confusing "No such file or directory"
error that looks unrelated to the real cause.

## Relevance to this project
If a `kolably_ui` CI failure mentions `kolably_backend` as a missing
working directory, or any step inside the "Checkout kolably-backend" /
downstream chain in `e2e-regression.yml` fails, **check whether
`BACKEND_REPO_TOKEN` is set in the repo's secrets first** — that's almost
certainly the actual cause, not whatever step's error message is visible.

Fix (requires GitHub account/org access this session doesn't have):
1. Create a fine-grained PAT scoped to read-only `contents:read` on
   `kolably/kolably-backend`.
2. Add it as a repository secret named `BACKEND_REPO_TOKEN` in
   `kolably_ui` → Settings → Secrets and variables → Actions.

See also `kolably_ui/e2e/README.md` for the broader e2e setup this
workflow is part of (hermetic `e2e/regression/` specs vs. the
live-dev-environment-only specs elsewhere in `e2e/`).

## Used in
- [[logs/2026-08-23]]
