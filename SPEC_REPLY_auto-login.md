# Server reply — `/auto-login` (token variant) — **IMPLEMENTED & LIVE**

**From:** Pi-server dev
**To:** desktop agent dev (現場Link / GenbaLink)
**Re:** `SPEC_REQUEST_app-auto-login.md` (2026-05-28 proposal)
**Status:** ✅ Approved with changes, implemented, tested, and deployed to `link.genbafms.com`.
**Date:** 2026-06-09.

---

## 0. TL;DR

Good idea, shipped it — but **as the token variant from your §6, not the raw-key version.** Putting the
API key in a browser URL would have written our highest-privilege, long-lived ingestion key into browser
history, the Nginx access log, our `agent_requests.jsonl`, and any Referer header the `/pdf/` page emits.
That key is the same one that authorizes **all** `/api/v1/*` ingestion, so we are not willing to expose it
in a URL. The 60-second single-use token costs you one extra round trip and keeps the real key in the
header where it belongs.

The flow is now **two calls**:

```
1.  POST /api/v1/auth/login-token      (X-API-Key in HEADER)   →  { "token": "...", "expires_in": 60 }
2.  GET  /auto-login?token=<token>&redirect=/pdf/gantt?date=…  →  302 + Set-Cookie: gbl_session=…
                                                                  →  browser lands on /pdf/… logged in
```

Everything below is the final contract as deployed.

---

## 1. What changed from your proposal (please read)

| Your proposal | What we shipped | Why |
| --- | --- | --- |
| `?api_key=<KEY>` in the URL | `?token=<one-time-token>` in the URL; key sent via header on a prior POST | Keep the long-lived API key out of history / logs / Referer |
| 30-day cookie `max_age` | **12-hour** cookie `max_age` | Matches our real session TTL (`GBL_SESSION_TTL_SECONDS = 12h`). Sessions are in-memory; a 30-day cookie would outlive the server session and silently log the user out anyway. Re-minted on every click, so the user still never sees a login form. |
| `Set-Cookie … Secure` set by app | `Secure` **not** set by FastAPI | Our existing `/api/auth/login` deliberately omits it and lets Nginx add `Secure` on the HTTPS hop. We matched that so behaviour is identical to the normal login. |
| "server picks the user associated with the API key" | session identity = the **API key label** (e.g. `APP`), `is_admin:false` | We have **no** api-key→human-user mapping. Keys map to a label, users live in a separate store. The session now carries the key label as a service identity. See §5. |

Naming: kept your `/auto-login` for the browser endpoint. The token-minting endpoint lives under the
existing agent namespace: `POST /api/v1/auth/login-token`.

---

## 2. Endpoint 1 — mint a token

```
POST /api/v1/auth/login-token
Headers:  X-API-Key: <your key>        ← header only, NEVER a URL
```

**Success (200):**

```json
{ "token": "PqL3…  (43-char urlsafe)", "expires_in": 60, "redirect_to": "/auto-login" }
```

**Errors:** `401 { "detail": "Missing or invalid X-API-Key header." }` — same auth as every other `/api/v1/*` call.

Token properties:
- **Single-use** — consumed on the first `/auto-login` hit; a second use returns 401.
- **60-second TTL** — mint it immediately before opening the browser.
- Opaque, `secrets.token_urlsafe(32)`. Carries no data; it's just a lookup key on the server.

---

## 3. Endpoint 2 — exchange token for a session

```
GET /auto-login?token=<token>&redirect=<relative-path>
```

**Success (302):**

```
HTTP/1.1 302 Found
Location:   /pdf/gantt?date=2026-06-09
Set-Cookie: gbl_session=<id>; HttpOnly; Max-Age=43200; Path=/; SameSite=Lax
```

(`Secure` appended by Nginx on the HTTPS hop.)

**Errors:**

| Status | When | Body |
| --- | --- | --- |
| 400 | `redirect` not a relative path (absolute URL, `//`, or `://`) | `{"detail":"redirect must be a relative path"}` |
| 400 | `redirect` loops back to `/auto-login` | `{"detail":"redirect may not loop back to /auto-login"}` |
| 400 | `redirect` not in the allowlist | `{"detail":"redirect not in allowlist"}` |
| 401 | token missing, expired, or already used | `{"detail":"Missing, expired, or already-used token"}` |

**Redirect allowlist (same-origin relative paths only):**

```
/pdf/
/dashboard
```

Anything else → 400. Tell us if you need `/reports`, `/m/`, or others added — it's a one-line change on
our side, we just kept the initial surface minimal.

---

## 4. Worked example

```
# 1. mint
POST https://link.genbafms.com/api/v1/auth/login-token
     X-API-Key: <key>
  → { "token": "PqL3xY…", "expires_in": 60 }

# 2. open in default browser
GET  https://link.genbafms.com/auto-login?token=PqL3xY…&redirect=%2Fpdf%2Fgantt%3Fdate%3D2026-06-09
  → 302 Location: /pdf/gantt?date=2026-06-09
    Set-Cookie: gbl_session=…; HttpOnly; Max-Age=43200; Path=/; SameSite=Lax
  → browser follows redirect WITH the cookie → /pdf/gantt renders, no login form
```

---

## 5. Agent-side change (replaces your §5)

It's now two steps instead of one. Suggested `main.js`:

```js
async function openPrintPage(pathWithQuery) {
  // 1. exchange the API key (header only) for a one-time token
  const res = await fetch(`${baseUrl}/api/v1/auth/login-token`, {
    method: 'POST',
    headers: { 'X-API-Key': settings.apiKey, 'X-Agent-Version': APP_VERSION },
  });
  if (!res.ok) { /* fall back to opening /login, or surface an error */ return; }
  const { token } = await res.json();

  // 2. open the browser via /auto-login — the token, not the key, is in the URL
  const redirect = encodeURIComponent(pathWithQuery);   // e.g. '/pdf/gantt?date=2026-06-09'
  shell.openExternal(`${baseUrl}/auto-login?token=${token}&redirect=${redirect}`);
}

// call sites
openPrintPage(`/pdf/gantt?date=${dateIso}`);
openPrintPage(`/pdf/summary?date=${dateIso}`);
```

Notes:
- Mint the token **right before** `openExternal` (60s window).
- One token = one browser open. If you open gantt + summary, mint twice.
- `X-Agent-Version` is logged (see §6).

---

## 6. Your open questions — answered

- **Naming** — kept `/auto-login` (public) + `POST /api/v1/auth/login-token` (agent namespace). ✅
- **Token instead of raw key** — **required, not optional.** Implemented exactly as your §6 best-practice variant. ✅
- **Per-user audit** — the session identity is the **API key label** (machine), not a human. If you need
  the operator, send `X-Agent-Operator: <windows-user>` and we can thread it into the session/log later —
  not wired yet. Say the word.
- **Cookie scope** — `Path=/`, `SameSite=Lax`, `HttpOnly`, `Max-Age=43200` (12h). Matches `/api/auth/login`
  exactly except for the shorter, correct TTL. ✅
- **Rate limiting** — reuses the existing `/api/v1/*` path; same protections, same logging.

---

## 7. Logging / audit

Both endpoints are logged to `agent_requests.jsonl` like any other agent call:
- `/auto-login` rows record the **token** and **redirect** (never the API key — it isn't in the URL).
- `X-Agent-Version` and `CF-Connecting-IP` captured.
- The token is single-use and 60s-lived, so logging it is harmless (already consumed).

---

## 8. Verification (done on our side, 2026-06-09)

| Check | Result |
| --- | --- |
| `login-token` without key | 401 |
| `login-token` with header key | token minted (43 chars) |
| `/auto-login` happy path | 302 + `gbl_session` cookie |
| reuse same token | 401 (single-use enforced) |
| `redirect=https://evil.example/…` | 400 |
| `redirect=/admin/secrets` (not allowlisted) | 400 |
| garbage token | 401 |
| issued cookie → `/api/auth/whoami` | `authenticated:true` |
| issued cookie → `/pdf/gantt` | renders, no login form |

Live now on `link.genbafms.com`. Wire up the agent side whenever you're ready — no further server work
needed unless you want more redirect prefixes or the `X-Agent-Operator` audit field.

— Pi-server dev
