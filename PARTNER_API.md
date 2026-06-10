# GENBA FMS — Partner Data API

Read-only, company-to-company API for retrieving production / attendance /
labor-productivity data. Issued and controlled by GENBA FMS admin.

---

## 1. Base URL

```
https://api.genbafms.com/v1
```

> Dedicated API host. `https://api.genbafms.com/v1/...` is the canonical base;
> `https://api.genbafms.com/partner/v1/...` also works (same endpoints). Only
> the partner API is reachable on this host — nothing else of the system is
> exposed here. Endpoint paths shown below as `/partner/v1/X` are reachable as
> **`/v1/X`** on `api.genbafms.com`.

## 2. Authentication

Every request **must** send your partner token:

```
Authorization: Bearer <YOUR_TOKEN>
```

(Alternatively: header `X-Partner-Token: <YOUR_TOKEN>`.)

- Tokens are issued **per company** and can be revoked at any time.
- A token may be restricted to specific source IPs and a request rate limit.
- Keep the token secret. Treat it like a password.

### Test credentials (sandbox — rotate/revoke before production)

```
Token : pt_IeNAMYtxlY8wbU1DKwf7vmDpWZHIVR14cmO3fQ
Rate  : 120 requests / minute
```

> This is a **TEST** token created for integration testing. GENBA FMS will
> issue you a dedicated production token and may revoke this test one anytime.

## 3. Quick test

```bash
curl -H "Authorization: Bearer pt_IeNAMYtxlY8wbU1DKwf7vmDpWZHIVR14cmO3fQ" \
     "https://api.genbafms.com/v1/ping"
# → {"ok":true,
#    "data":{"pong":true,"server_time":"2026-05-19T12:50:46"},
#    "meta":{"partner":"TEST partner","ts":"...","api_version":"...","cached":false}}
```

> **Response envelope.** Every response is wrapped as
> `{ "ok": true, "data": <payload>, "meta": { "partner", "ts", "api_version",
> "cached", ... } }`. The per-endpoint examples in §4 show only the **`data`**
> payload. List endpoints (`packs`, `attendance`, `datasets`) accept
> `?limit=&offset=` and add pagination keys to `meta`. Responses carry an
> `ETag` + `Cache-Control`; send `If-None-Match` to get a `304`.

Ready-to-open test links (add the `Authorization` header — browsers can't set
it, so use curl/Postman/your HTTP client):

| Link | What it returns |
| --- | --- |
| `https://api.genbafms.com/v1/ping` | Auth check + server time |
| `https://api.genbafms.com/v1/datasets` | List of available datasets |
| `https://api.genbafms.com/v1/productivity?range=month` | Labor productivity series + summary |
| `https://api.genbafms.com/v1/production?date=2026-05-19` | Production + section summary for a date |
| `https://api.genbafms.com/v1/packs?date=2026-05-19` | Per-item produced-packs rows for a date |
| `https://api.genbafms.com/v1/attendance?date=2026-05-19` | Per-employee attendance + per-section/grand totals for a date |

## 4. Endpoints

All endpoints are **GET**, read-only, and require the `Authorization` header.

### `GET /partner/v1/ping`
Health/auth check.
```json
{ "ok": true, "partner": "TEST partner", "server_time": "2026-05-19T12:50:46" }
```

### `GET /partner/v1/datasets`
Discovery — lists the data endpoints available to you.

### `GET /partner/v1/production?date=YYYY-MM-DD`
Production totals + section/productivity summary + plan for a date.
`date` optional (defaults to the latest report date).
```jsonc
{
  "report_date": "2026-05-19",
  "today":       { "total_packs": 286859, ... },
  "productivity":{ "sections": [ { "id":1, "label":"製造１課", "lp": 100.36, ... } ], ... },
  "plan":        { "lines": [ ... ], "total_planned": ... }
}
```

### `GET /partner/v1/productivity?range=&end=`
Labor-productivity series + summary.
`range` = `day` | `week` | `month` | `3month` (default `month`).
`end` = ISO date (optional; default latest).
```jsonc
{
  "range": "month",
  "current":  { "start":"...", "end":"...",
                "summary": { "lp_s1":..., "lp_s2":..., "lp_combined":...,
                             "total_hours_s1":..., "total_hours_s2":...,
                             "total_hours_combined":..., "total_packs":... },
                "series":  { "labels":[...], "lp_s1":[...], "lp_s2":[...],
                             "lp_combined":[...], "packs":[...] } },
  "previous": { ...same shape (prior period) }
}
```
Targets (fixed): S1 = 85 P/h, S2 = 35 P/h, Combined = 25 P/h.

### `GET /partner/v1/packs?date=YYYY-MM-DD`
Per-item produced-packs rows for the given date (`date` required).
Accepts `?limit=&offset=` for pagination.

### `GET /partner/v1/attendance?date=YYYY-MM-DD`
Per-employee attendance for a date: name, code, section, in/out times, worked
hours (`hours` HH:MM + `minutes`), `is_temp` flag — plus per-section and grand
totals. `date` required. Optional `section=1|2` filter and `?limit=&offset=`.
```jsonc
{
  "date": "2026-05-19",
  "employees": [ { "name":"…", "code":"…", "section_id":1, "section":"製造１課",
                   "in":"…", "out":"…", "hours":"8:00", "minutes":480, "is_temp":false } ],
  "totals": { "employees":…, "present":…, "total_hours_hhmm":"…", "total_hours":…,
              "by_section":[ { "id":1, "label":"製造１課", "employees":…, "present":…,
                               "total_hours_hhmm":"…", "total_hours":… } ] }
}
```

## 5. Rate limits & errors

| Status | Meaning | What to do |
| --- | --- | --- |
| `200` | OK | — |
| `401` | Missing/invalid token | Send the `Authorization: Bearer` header with a valid token |
| `403` | Token disabled, or source IP not allowed | Contact GENBA FMS admin |
| `429` | Rate limit exceeded (per-minute) | Back off, retry after ~60s |
| `503` | Partner API disabled by admin | Temporary; retry later |
| `502` | Upstream data temporarily unavailable | Retry shortly |

Recommended client behavior: send the token on every call; on `429`/`503`/`502`
back off and retry; never hammer in a tight loop.

## 6. Security model (FYI)

- **Read-only**, curated datasets only — production / attendance summary /
  labor productivity. No user accounts, credentials, API keys, or internal
  config are reachable through this API, by design.
- The whole API is **deny-by-default**: off unless explicitly enabled, and no
  data without a valid per-partner token.
- Each partner token: individually revocable, optional IP allowlist, per-minute
  rate limit. All calls are logged server-side for audit.

## 7. Support / changes

Token issuance, rate/IP changes, and revocation are handled by GENBA FMS admin
(**/admin → Partner API**). If the contract changes, this document is updated
and re-served at `/admin/partner-spec`.
