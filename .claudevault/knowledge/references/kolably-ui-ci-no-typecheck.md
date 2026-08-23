# kolably_ui's CI does not typecheck or build — only lint + unit test

parent:: [[context]]
source:: discovered diagnosing the `requestResync` ReferenceError production incident
date:: 2026-08-23
saved-because:: a real TypeScript compile error (`Cannot find name 'requestResync'`) shipped to production because of this gap — confirmed concretely, not theoretical. Any future session evaluating "is this change safe to push" should know CI won't catch type errors.

## Summary
`kolably_ui/.github/workflows/ci.yml` runs exactly two steps on push/PR to
`main`: `npm run lint` (ESLint) and `npm run test` (Vitest unit tests). It
does **not** run `tsc --noEmit` and does **not** run `npm run build` (`vite
build`, which also does not type-check by default in this Vite/React setup
— Vite transpiles with esbuild, stripping types without verifying them).

Confirmed concretely: commit `b96efde` referenced `requestResync` — an
undefined identifier — inside `resyncConversation()` in both
`InboxView.tsx` files. This is `TS2304: Cannot find name 'requestResync'`,
an unconditional compile error under any TypeScript config. It passed CI
(lint didn't flag it, no typecheck step existed to catch it), merged to
`main`, deployed to production, and crashed the Inbox page for every user
with `ReferenceError: requestResync is not defined` until diagnosed and
fixed in `795db50`. See [[logs/2026-08-23]] for the full incident.

## Relevance to this project
- **Before trusting that a `kolably_ui` change is safe because "CI is
  green," know that CI does not verify TypeScript correctness at all.**
  Manually run `npx tsc --noEmit -p tsconfig.json` (and ideally `npm run
  build`) before pushing anything non-trivial to this repo, especially
  anything touching hooks/callbacks with dependency arrays referencing
  external names — exactly the pattern that broke here.
- This is a concrete gap worth surfacing to the user for
  `.github/workflows/ci.yml`: adding a `tsc --noEmit` (and/or `vite build`)
  step would have caught this specific incident before merge, not just
  before deploy.
- Same likely applies to the `mobile/` React Native app's own CI/build
  setup — not verified in this session, but the equivalent bug shipped
  there too (`b96efde` touched `mobile/hooks/useConversationRealtime.ts`
  and `mobile/app/chat-thread.tsx`, fixed separately in `3f161ec`) —
  suggests the same missing-typecheck gap may exist there too.

## Used in
- [[logs/2026-08-23]] — the incident this was discovered during.
