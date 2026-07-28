# Frontend Integration — Google & Instagram Login

Backend facade pattern applies here too: the frontend never talks to Supabase
or Meta's token endpoints directly. It only ever (1) sends the user to a
provider's consent screen, (2) catches the redirect back with a `code`/token,
and (3) hands that to our API, which does the rest and returns our own
session tokens (`access_token`/`refresh_token`, same shape as email/password
login).

---

## 1. Google Sign-In

```
POST /api/v1/auth/google
{ "id_token": str, "role"?: "creator" | "business" }
→ { access_token, refresh_token, token_type: "bearer", user: {...}, is_new_user: bool }
```

1. Frontend uses Google Identity Services (or the native Google Sign-In SDK
   on mobile) to get an **ID token** — this step never touches our backend.
2. POST that `id_token` to `/auth/google`. Include `role` only if you know
   this might be the user's first sign-in (harmless to always send it —
   it's ignored for returning users).
3. If `is_new_user: true`, route to a profile-completion step (`PATCH
   /auth/me`) — Google only gives us name/avatar, nothing else.
4. Store `access_token`/`refresh_token` the same way you already do for
   email/password login. Same `/auth/refresh` and `/auth/logout` endpoints
   apply.

No frontend env var needed for the backend call itself — but Google Sign-In
itself needs a **Google OAuth Client ID** (web, and iOS/Android if native)
registered in **Supabase Dashboard → Authentication → Providers → Google →
Authorized Client IDs**. Ask if those aren't set up yet.

---

## 2. Instagram — two different flows, don't mix them up

| | Direct signup/login | Connect (onboarding) |
|---|---|---|
| Who | New or returning creator, no account yet | Already-signed-up creator (Google/email) |
| Endpoint | `POST /auth/instagram` | `POST /creators/me/instagram/connect` |
| Auth required | No (this *is* the login) | Yes (Bearer token) |
| Result | Full pre-fill + portfolio import + a session | Same pre-fill, applied to the existing account |

Both use the **same OAuth mechanics** (Instagram's authorize URL → code →
one of the two endpoints above), just triggered from different places:
a "Continue with Instagram" button on the signup screen vs. a "Connect
Instagram" button during onboarding for creators who signed up another way.

### 2a. Building the authorize URL

```
https://www.instagram.com/oauth/authorize
  ?client_id=<INSTAGRAM_APP_ID>
  &redirect_uri=<REDIRECT_URI>
  &scope=instagram_business_basic,instagram_business_manage_insights
  &response_type=code
```

- `INSTAGRAM_APP_ID` is public (like any OAuth client_id) — safe to embed in
  frontend code. Current value: `2773696536339636` — pull the live value
  from the backend's `.env` (`INSTAGRAM_APP_ID`) if it's ever rotated.
- `redirect_uri` **must exactly match** what's registered in the Meta App
  Dashboard, including trailing slash: `https://kolably.com/` in production,
  `https://localhost:8080/` for local dev. No path — just the root. This is
  a hard Meta requirement (exact string match, not a prefix).

`window.location.href = <that URL>` to send the user there. Instagram
redirects back to `redirect_uri` with `?code=...`.

### 2b. Handling the redirect back

Since **both flows share the same exact `redirect_uri`**, the app needs to
know which one is in progress when it reloads at `https://kolably.com/?code=...`.
Set a flag right before redirecting out, read it on load:

```js
// Before redirecting to Instagram:
sessionStorage.setItem("ig_oauth_intent", "signup"); // or "connect"
window.location.href = authorizeUrl;

// On app load, at the redirect target:
const code = new URLSearchParams(window.location.search).get("code");
if (code) {
  const intent = sessionStorage.getItem("ig_oauth_intent");
  sessionStorage.removeItem("ig_oauth_intent");
  // strip ?code= from the URL, then call the right endpoint per `intent`
}
```

### 2c. Direct signup/login

```
POST /auth/instagram
{ "code": str, "redirect_uri": str, "role"?: "creator" }
→ { access_token, refresh_token, token_type, user, is_new_user }
```

- `role: "creator"` required on first sign-in only (400 if missing) — always
  safe to send it, it's ignored for returning users. There's no `business`
  option; only creators use Instagram login.
- `is_new_user: true` means the account was just created with a full
  pre-fill (name, bio, website, photo, follower/following counts,
  engagement rate) **and** recent posts already imported into their
  portfolio — no separate onboarding step needed, just drop them into the
  app.
- Store tokens exactly like the Google/email flows.

### 2d. Connect flow (Google/email creators, during onboarding)

```
GET  /creators/me/instagram/auth-url?redirect_uri=<...>   (Bearer auth)
→ { "url": str }
```
Call this instead of building the URL yourself here — same URL, but it's a
convenience since the user is already logged in.

```
POST /creators/me/instagram/connect   (Bearer auth)
{ "code": str, "redirect_uri": str }
→ CreatorResponse   (full profile, now instagram_connected: true)
```

Possible error responses to handle:
| Status | Meaning |
|---|---|
| 404 | No creator profile for this account |
| 422 | Instagram account is Personal, not Business/Creator — tell them to convert it first |
| 409 | That Instagram account is already connected to a *different* Kolably account |

Two more endpoints for later in the profile lifecycle (Bearer auth, no body needed):
```
POST   /creators/me/instagram/sync              → CreatorResponse   (refresh stats only)
DELETE /creators/me/instagram/disconnect        → 204
POST   /creators/me/instagram/import-portfolio  → list[PortfolioItemResponse]
```
Call `sync` when viewing your own profile if `instagram_synced_at` is more
than ~24h old — it only refreshes follower/following count, photo, and
engagement rate, not name/bio/website (those are one-time pre-fill so a
creator's manual edits don't get silently overwritten).

### 2e. The mandatory onboarding gate

Creators who sign up via Google/email have no Instagram data yet. Check
`instagram_connected` on their `CreatorResponse` (or `GET /auth/me`) right
after signup and route them to the connect screen before letting them use
the app. Once creator-action endpoints exist (applying to campaigns,
submitting content, etc.), they'll also enforce this server-side — a 403
with `detail: "instagram_not_connected"` means: redirect to the connect
screen, don't just show a generic error.
