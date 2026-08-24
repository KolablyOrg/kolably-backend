# Verify a backend deploy actually landed via GitHub Actions run history, don't assume push = live

parent:: [[context]]
source:: diagnosing a user report that the #31 (deactivated-account password-reset) fix wasn't working
date:: 2026-08-24
saved-because:: a real deploy failure created a window where neither of two independent fixes for the same bug was actually live, and the fix looked broken by data/logic review alone — the backend's own deploy history was what actually explained it. This is the backend-side sibling of [[knowledge/references/kolably-ui-vercel-deploy-gap]] (which is Vercel/kolably_ui-specific) — same principle, different mechanism, worth its own note since the verification technique is completely different.

## Summary
`kolably_backend` deploys via `.github/workflows/deploy.yml`: a `test` job
(ruff + pytest + hermetic Supabase integration tests) gates a `deploy` job
that tars the repo, ships it to EC2 over SSH, and does a full
`docker build --no-cache` + container replace + nginx reload. **A push to
`main` triggering this workflow is not the same as the deploy having
succeeded** — confirmed concretely: commit `539441e` (a fix for #31) had
its `Deploy Backend` **workflow run fail** even though the commit itself
was on `main`, creating a real window where production ran neither that
fix nor a later, independently-written equivalent, until a subsequent
commit's deploy (`8152f3c`) actually succeeded ~35 minutes later. A user
report of "the fix isn't working" during that window looked exactly like a
code bug — data was clean (verified via direct SQL against the live
`profiles`/`auth.users` tables), logic was correct — but the real cause was
purely a deploy gap.

## How to check
```sh
gh run list --repo KolablyOrg/kolably-backend --limit 8 \
  --json databaseId,name,workflowName,conclusion,headSha
```
Look for **two** rows per commit (`Deploy Backend` and `Fetch Prod Logs` are
separate workflows here) — `conclusion` on the `Deploy Backend` row is the
one that matters; `"failure"` means that exact commit's code never actually
reached the EC2 container, regardless of what the commit itself contains.
Get precise timing (to compare against when a user says they tested) with:
```sh
gh run view <databaseId> --repo KolablyOrg/kolably-backend \
  --json status,conclusion,createdAt,updatedAt,headSha
```
`updatedAt` on a `"conclusion":"success"` run is the actual moment the new
container went live (this workflow's `deploy` job runs sequentially after
`test`, and does a real `docker run` replace at the end — a green run
genuinely means new code is serving, not just "checks passed").

## Relevance to this project
**Before concluding a backend fix "isn't working" from a user report, check
`gh run list` for that commit's `Deploy Backend` conclusion before
re-diagnosing the code.** A failed deploy looks identical to a code bug
from the outside (the old behavior just keeps happening), but no amount of
re-reading the source or re-checking live data will explain it — the
running container simply isn't executing the code being reviewed. Doubly
worth checking when two sessions raced to fix the same issue (as here) —
the first attempt's deploy failing while a later one's succeeds is exactly
the kind of thing that's invisible unless you check run history directly.

## Used in
- [[logs/2026-08-24]]
