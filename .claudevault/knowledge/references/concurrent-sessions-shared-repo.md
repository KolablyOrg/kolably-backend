# Multiple concurrent Claude Code sessions share this working directory

parent:: [[context]]
source:: discovered while pushing [[decisions/002-notifications-realtime-via-supabase]]
date:: 2026-08-23
saved-because:: nearly caused pushing/committing another session's in-progress, unreviewed work as if it were mine — this is a standing operational hazard in this repo, not a one-off, and the safe procedure is non-obvious enough to be worth codifying.

## Summary
This repo (and its sibling `kolably_ui`) is worked on by **multiple Claude
Code sessions concurrently on the same local checkout** — confirmed via
`ListAgents` showing peer sessions (`kolably-3b`, `kolably-be`, etc.) and,
concretely, by the working tree containing substantial uncommitted/unpushed
changes I never made: staged renames of two migration files, modified
`.github/workflows/deploy.yml` and `app/services/collaboration_service.py`,
several new untracked migrations, `tests_integration/`, `.env.e2e-local*`,
`scripts/seed_e2e_fixtures.py`. On the remote side, `git push` was rejected
twice (backend and `kolably_ui`) because other sessions had already pushed
unrelated features (chat history caching, mobile auth/redirect fixes)
between my last fetch and my push attempt.

## Relevance to this project
**Before committing or pushing in this repo, always assume other sessions
are concurrently mutating the same working directory and remote.** Concretely:

1. **Never `git add -A` / `git add .`** — always stage and commit specific
   files by path. Blanket-add will scoop up another session's in-progress,
   unreviewed changes into your commit.
2. **`git commit <pathspec>...`** (naming the exact files, not just
   `git commit -m`) commits only those paths' changes even if something else
   is sitting staged in the index — this is what let me commit my
   notification-realtime files without touching the concurrently-staged
   migration renames.
3. **Expect `git push` to be rejected** (fetch first) — this is normal here,
   not an error state. Fetch, then check for *actual* line-level overlap
   with your own changed files before assuming a conflict — a file showing
   up in `git diff HEAD..origin/main --stat` does not by itself mean the
   remote changed it; it may just mean your own uncommitted-to-origin
   changes are the entire diff. Confirm with
   `git diff $(git merge-base HEAD origin/main)..origin/main -- <file>`
   before worrying.
4. **If a plain `git merge origin/main` is blocked by someone else's
   uncommitted changes** ("your local changes would be overwritten"), don't
   discard them. `git stash push -m "..."` (default, tracked changes only,
   no `--include-untracked` needed since untracked files don't block
   merges), do the merge, then `git stash pop` immediately after — this
   restores their in-progress state exactly, untouched, ready for whichever
   session owns it to resume.
5. Prefer a plain `git merge` over `git rebase` when pulling in remote
   changes here — rebase would rewrite commit history that other sessions
   may already have fetched/be working atop.

## Confirmed risk, not just theoretical
Within the same session, a concurrent commit (`kolably_ui` `5ce87b3`, "Add
local chat thread cache and delta sync") introduced a one-character logic
bug (`||` flipped to `&&` in a JSX render guard) that broke the Inbox page
in production — `Something went wrong. Please refresh the page.` — silently
enough that `tsc --noEmit` and `vite build` both stayed green before and
after (it's a boolean-logic bug, not a type error). **Lesson: after merging
in another concurrent session's changes, don't just typecheck/build — those
only catch a subset of regressions.** If the user reports something broken
shortly after a push that included a merge, check what the *other* side of
that merge actually changed (`git show <their-commit>`) before assuming the
bug is in your own work.

## Used in
- [[decisions/002-notifications-realtime-via-supabase]] — the push this
  procedure was worked out for, and where the confirmed-risk incident
  (Inbox crash) happened.
- [[logs/2026-08-23]]
