# GENBA FMS Partner API — Step-by-Step Test Guide (v1.1)

A human-readable QA walkthrough. Follow top-to-bottom; each step has a
**command**, the **expected result**, and a **✅ Pass** check.

> Convert to PDF if needed: open in VS Code / any Markdown viewer → Print → Save as PDF,
> or `pandoc PARTNER_API_TEST_GUIDE.md -o PartnerAPI_TestGuide.pdf`.

---

## 0. Before you start

| You need | Value |
|---|---|
| Admin panel | `https://link.genbafms.com/admin` (password from the team) |
| Public API base | `https://api.genbafms.com/v1` (canonical) — `…/partner/v1` also works |
| On-Pi base (LAN/SSH testing) | `http://127.0.0.1:8002/partner/v1` |
| Partner token | created in Step 1 (looks like `pt_XXXXXXXX…`) |
| Tools | `curl` (CLI), or Postman/Insomnia, plus a browser for Swagger UI |

Conventions used below:

```bash
BASE="https://api.genbafms.com/v1"          # or http://127.0.0.1:8002/partner/v1
TOKEN="pt_PASTE_YOUR_TOKEN_HERE"
AUTH=(-H "Authorization: Bearer $TOKEN")
```

Status-code map: `200` ok · `304` not-modified (cache) · `401` token problem ·
`403` partner disabled / IP blocked · `429` rate-limit or quota · `503` API
disabled · `502` upstream hiccup.

---

## 1. Enable the API & create a test partner

1. Open `https://link.genbafms.com/admin` → log in → **Agent**… no, the **Partner API** tab.
2. If the status pill says **DISABLED**, click **Enable API** (confirm).
   - ✅ Pass: pill turns **ENABLED**.
3. In *Add partner*: enter a name (e.g. `QA Test`), `rate/min` = `120`,
   `quota/mo` = `0`, leave IP allowlist blank → **Add partner**.
   - ✅ Pass: a one-time token banner appears: `Token for "QA Test" … pt_…`.
4. **Copy the token** into `TOKEN` above. It is shown only once.
   - ✅ Pass: a row for `QA Test` appears in the partner table.

---

## 2. Authentication

| # | Command | Expected | ✅ Pass |
|---|---|---|---|
| 2.1 | `curl -s "$BASE/ping"` | `401` `{"ok":false,"error":{"code":"missing_token",…}}` | no-token rejected |
| 2.2 | `curl -s -H "Authorization: Bearer pt_WRONG" "$BASE/ping"` | `401` `code:"invalid_token"` | bad token rejected |
| 2.3 | `curl -s "${AUTH[@]}" "$BASE/ping"` | `200` enveloped (see §3) | valid token works |

```bash
curl -s "${AUTH[@]}" "$BASE/ping" | python3 -m json.tool
```

---

## 3. Response envelope (success shape)

Run: `curl -s "${AUTH[@]}" "$BASE/ping"`

Expected body:

```json
{
  "ok": true,
  "data": { "pong": true, "server_time": "…" },
  "meta": { "partner": "QA Test", "ts": "…", "api_version": "1.1", "cached": false }
}
```

✅ Pass: top-level keys are exactly `ok`, `data`, `meta`; `ok` is `true`;
`meta.api_version` = `1.1`.

---

## 4. Error codes

| # | Command | Expected HTTP | Expected `error.code` |
|---|---|---|---|
| 4.1 | no token (`$BASE/ping`) | 401 | `missing_token` |
| 4.2 | bad token | 401 | `invalid_token` |
| 4.3 | (after Step 11 disable partner) | 403 | `partner_disabled` |
| 4.4 | exceed rate limit (§7) | 429 | `rate_limited` |
| 4.5 | exceed quota (§8) | 429 | `quota_exceeded` |
| 4.6 | API disabled (§12) | 503 | `api_disabled` |

✅ Pass: every error is the envelope `{"ok":false,"error":{"code","message"}}`
with the matching HTTP status.

---

## 5. Caching (ETag / 304)

```bash
# 5.1 capture the ETag
ETAG=$(curl -s -D - -o /dev/null "${AUTH[@]}" "$BASE/productivity?range=month" \
       | awk -F': ' 'tolower($1)=="etag"{print $2}' | tr -d '\r')
echo "ETag=$ETAG"

# 5.2 re-request with If-None-Match
curl -s -o /dev/null -w "%{http_code}\n" "${AUTH[@]}" \
     -H "If-None-Match: $ETAG" "$BASE/productivity?range=month"
```

- ✅ 5.1 Pass: response has `ETag:` and `Cache-Control: private, max-age=60`.
- ✅ 5.2 Pass: returns **304** (empty body) when the ETag matches.

---

## 6. Pagination (`limit` / `offset`)

```bash
curl -s "${AUTH[@]}" "$BASE/datasets?limit=2&offset=1" | python3 -m json.tool
```

✅ Pass: `meta` contains `total`, `offset`, `limit`, `returned`
(e.g. `total:3, offset:1, limit:2, returned:2`) and `data` has 2 items.
Also try `"$BASE/packs?date=YYYY-MM-DD&limit=5&offset=0"`.

---

## 7. Rate limiting

Set the test partner's `rate/min` low first (admin → table → set it via
**Add** a fresh partner with `rate/min`=`3`, or keep 120 and loop hard).

```bash
for i in $(seq 1 130); do \
  curl -s -o /dev/null -w "%{http_code} " "${AUTH[@]}" "$BASE/ping"; done; echo
```

✅ Pass: first N (= rate/min) return `200`, then `429` with
`error.code:"rate_limited"` and a `Retry-After` header. Wait 60 s → `200` again.

---

## 8. Monthly quota

1. Admin → Partner API → the partner's row → **Quota** button → set `5`.
2. Call `$BASE/ping` repeatedly until it flips.

```bash
for i in $(seq 1 8); do \
  curl -s -o /dev/null -w "%{http_code} " "${AUTH[@]}" "$BASE/ping"; done; echo
curl -s "${AUTH[@]}" "$BASE/ping"        # show the body once over quota
```

- ✅ Pass: once the month total reaches the quota → **429**
  `error.code:"quota_exceeded"`, `Retry-After: 3600`.
- ✅ Pass: admin table **Usage t/mo** column reflects the climbing count.
- **Reset:** Quota button → `0` (unlimited). Confirm `$BASE/ping` → `200` again.

---

## 9. Data endpoints (sanity)

| # | Command | Expected |
|---|---|---|
| 9.1 | `curl -s "${AUTH[@]}" "$BASE/datasets"` | 200, lists production/productivity/packs |
| 9.2 | `curl -s "${AUTH[@]}" "$BASE/production?date=2026-05-19"` | 200, `data` has report_date/today/productivity/plan |
| 9.3 | `curl -s "${AUTH[@]}" "$BASE/productivity?range=month"` | 200, `data` has current/previous/series |
| 9.4 | `curl -s "${AUTH[@]}" "$BASE/packs?date=2026-05-19"` | 200, per-item rows |

✅ Pass: all `200`, all wrapped in the `{ok,data,meta}` envelope, **no**
user / token / config fields anywhere in `data`.

---

## 10. OpenAPI & Swagger UI

| # | Action | Expected | ✅ Pass |
|---|---|---|---|
| 10.1 | `curl -s "$BASE/openapi.json"` | 200 `application/json`, valid OpenAPI 3.0 | spec served (no token needed) |
| 10.2 | Browser → `https://api.genbafms.com/v1/docs` | Swagger UI loads | endpoints listed |
| 10.3 | In Swagger UI → **Authorize** → paste `pt_…` → "Try it out" on `/ping` | 200 enveloped | interactive call works |

---

## 11. Admin tab controls

1. **Usage**: confirm the partner row shows climbing `Usage t/mo` and `Calls`,
   plus `Last seen`. ✅
2. **Disable a partner**: row → **Disable** → `curl "${AUTH[@]}" "$BASE/ping"`
   → **403 `partner_disabled`**. Re-enable → `200`. ✅
3. **Request log**: bottom table shows every call (partner, IP, path, status).
   ✅ each test call you ran is listed.
4. **Revoke**: create a throwaway partner, **Revoke** it, then its token →
   **401 `invalid_token`**. ✅

---

## 12. Global kill-switch (⚠️ affects real partners)

> Do this only in a maintenance window — it stops **all** partners.

1. Partner API tab → **Disable API**.
2. `curl -s -o /dev/null -w "%{http_code}\n" "${AUTH[@]}" "$BASE/ping"` → **503**
   `error.code:"api_disabled"`.
3. **Re-enable** → `$BASE/ping` → **200**.

✅ Pass: disabled = 503 for everyone; re-enable restores service; setting
persists across an app restart.

---

## 13. Public host lock-down (`api.genbafms.com`)

| # | Command | Expected | ✅ Pass |
|---|---|---|---|
| 13.1 | `curl -s -o /dev/null -w "%{http_code}" https://api.genbafms.com/v1/ping` (no token) | 401 | API reachable, token-gated |
| 13.2 | `…/v1/ping` with token | 200 | works on public host |
| 13.3 | `https://api.genbafms.com/admin` | **404** | admin NOT exposed here |
| 13.4 | `https://api.genbafms.com/dashboard` | **404** | app NOT exposed here |
| 13.5 | `https://api.genbafms.com/api/v1/ping` | **404** | desktop API NOT exposed here |

✅ Pass: only `/v1` (and `/partner/v1`, `/api/health`) respond; everything
else is 404 on the partner subdomain.

---

## 14. Cleanup / restore

- [ ] Reset the test partner quota to `0` (unlimited).
- [ ] Revoke any throwaway partners created during testing.
- [ ] Confirm Partner API status pill = **ENABLED** (production state).
- [ ] Confirm the real desktop ingestion is **active** (Agent tab — not deactivated).

---

## Appendix A — quick smoke test (copy-paste)

```bash
BASE="https://api.genbafms.com/v1"; TOKEN="pt_PASTE"; AUTH=(-H "Authorization: Bearer $TOKEN")
echo "no-token : $(curl -s -o /dev/null -w '%{http_code}' "$BASE/ping")            # 401"
echo "valid    : $(curl -s -o /dev/null -w '%{http_code}' "${AUTH[@]}" "$BASE/ping")  # 200"
echo "openapi  : $(curl -s -o /dev/null -w '%{http_code}' "$BASE/openapi.json")     # 200"
echo "locked   : $(curl -s -o /dev/null -w '%{http_code}' https://api.genbafms.com/admin)  # 404"
curl -s "${AUTH[@]}" "$BASE/ping" | python3 -m json.tool
```

## Appendix B — troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `401 missing_token` | no/blank Authorization header | send `Authorization: Bearer pt_…` |
| `401 invalid_token` | wrong/revoked token | re-issue in admin |
| `401 {"detail":"authentication required"}` (not enveloped) | hit a non-`/partner/v1` path on a login-gated host | use `https://api.genbafms.com/v1/...` |
| `403 ip_not_allowed` | partner has an IP allowlist | add caller IP in admin, or clear allowlist |
| `429 rate_limited` | >rate/min | back off; honour `Retry-After` |
| `429 quota_exceeded` | monthly quota hit | raise/clear quota in admin |
| `503 api_disabled` | kill-switch off | enable in admin Partner API tab |
| `502 upstream_unavailable` | internal data endpoint hiccup | retry shortly; check app health |

*End of guide — Partner API v1.1.*
