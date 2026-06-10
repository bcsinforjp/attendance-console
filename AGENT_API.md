# AI-Agent API — Integration Manual

For external AI agents that connect to the GENBA FMS server with a **single bearer
token** to read/write factory data and to run a **change-management workflow**
(request → evaluate → approve → implement → feedback).

One token, two front doors:

| Front door | Base URL | For |
| --- | --- | --- |
| **REST** | `https://link.genbafms.com/api/agent/v1` | scripts, HTTP clients |
| **MCP** | `https://link.genbafms.com/mcp` | LLM agents (Model Context Protocol — tools auto-discovered) |

> **Deny-by-default.** The API is off until an admin enables it, and nothing
> works without a per-agent token. Each token is individually **revocable,
> rate-limited, and IP-allowlistable**, and can be flipped **read-only**.

---

## 1. Authentication

Send your token on **every** request, in the header (never in a URL):

```
Authorization: Bearer at_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

(Alternatively `X-Agent-Token: at_…`.) Tokens are issued by the admin in
**/admin → Agent API → Add agent** and shown once.

### Quick test
```
curl -H "Authorization: Bearer at_…" https://link.genbafms.com/api/agent/v1/ping
```
```json
{"ok":true,"data":{"pong":true,"write_enabled":true,"server_time":"..."},"meta":{"agent":"acme","api_version":"1.0"}}
```

---

## 2. Response envelope & errors

Every REST response is enveloped:
```json
{ "ok": true, "data": { ... }, "meta": { "agent": "...", "ts": "...", "api_version": "1.0" } }
```
Read responses carry an `ETag`; resend it as `If-None-Match` to get a `304`.

Errors:
```json
{ "ok": false, "error": { "code": "invalid_token", "message": "Invalid agent token." } }
```

| Status | code | Meaning / action |
| --- | --- | --- |
| 401 | `missing_token` / `invalid_token` | Provide/fix the bearer token |
| 403 | `agent_disabled` | Token disabled by admin |
| 403 | `ip_not_allowed` | Your IP isn't in the token's allowlist |
| 403 | `write_disabled` | Token is read-only; ask admin to enable write |
| 429 | `rate_limited` | Slow down (see `Retry-After`) |
| 503 | `api_disabled` | Admin has not enabled the API |
| 400 | `bad_request` | Invalid payload (see message) |
| 423 | `ingestion_paused` | Admin paused ingestion; retry later |
| 502 | `upstream_unavailable` | Server-side data/write path error |

---

## 3. Read endpoints (`GET`)

| Path | Returns |
| --- | --- |
| `/api/agent/v1/ping` | token check + server time |
| `/api/agent/v1/datasets` | self-describing capability list |
| `/api/agent/v1/production?date=YYYY-MM-DD` | production + productivity snapshot (date optional → latest) |
| `/api/agent/v1/productivity?range=day\|week\|month\|3month&end=YYYY-MM-DD` | labor-productivity series + prior period |
| `/api/agent/v1/packs?date=YYYY-MM-DD` | per-item produced-packs rows |
| `/api/agent/v1/attendance?date=YYYY-MM-DD&section=1\|2` | per-employee attendance + per-section/grand totals |
| `/api/agent/v1/roster?section=all\|1\|2` | employee roster (read-only) |
| `/api/agent/v1/dayoff` | day-off schedule (read-only) |
| `/api/agent/v1/packs/{date}/history` | pack-count audit trail for a date |

List endpoints accept `?limit=&offset=` and report pagination in `meta`.

---

## 4. Write endpoints (`POST`) — require `write_enabled`

Writes are limited to **pack counts** and **temp-staff**. All writes are
audit-logged server-side (pack changes appear in the history endpoint).

```
POST /api/agent/v1/packs
{ "record_date": "2026-06-08", "number_of_packs": 1234, "note": "optional" }

POST /api/agent/v1/packs/bulk
{ "entries": [ { "record_date": "2026-06-08", "number_of_packs": 1234, "note": "" }, ... ] }

POST /api/agent/v1/temp-staff
{ "record_date": "2026-06-08", "rows": [ { "headcount": 3, "start_time": "08:00", "leave_time": "17:00", "company": "Fullcast" } ] }
```

> **Date rule:** report date = production date = attendance (shift) date **+ 1**.
> Fullcast/temp-staff are keyed on the **shift** date. When in doubt, read
> `/api/agent/v1/production` to see the current report/production date.

> **Not available to agents:** deletes/cleanup, roster &amp; day-off writes,
> file uploads, and any user/key/admin operation. Need one of these? File a
> **change request** (§6).

---

## 5. MCP (Model Context Protocol)

`POST https://link.genbafms.com/mcp` speaks JSON-RPC 2.0 over plain HTTP
(request/response; no SSE needed). Send the **same** `Authorization: Bearer`
header on every call. Methods: `initialize`, `tools/list`, `tools/call`.

```
curl -X POST https://link.genbafms.com/mcp -H "Authorization: Bearer at_…" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

### Connecting a Claude client
Add an HTTP MCP server pointing at `https://link.genbafms.com/mcp` with an
`Authorization: Bearer at_…` header. The client will auto-discover the tools below.

### Tools
**Read:** `get_production`, `get_productivity`, `get_packs`, `get_attendance`,
`get_roster`, `get_dayoff_schedule`, `get_packs_history`.
**Write (needs write access):** `set_pack_count`, `set_pack_counts_bulk`, `set_temp_staff`.
**Change management:** `submit_change_request`, `list_my_requests`, `get_request`,
`post_request_message`, `post_request_feedback`.

Tool arguments mirror the REST bodies above. A failed tool returns
`{ "isError": true, "content": [{ "type": "text", "text": "code: message" }] }`.

---

## 6. Change-Management workflow

When you need a capability the API doesn't provide, submit a **change request**.
An admin evaluates feasibility, risk, and a timeline, approves or rejects, a human
implements it on the server, and you report back. You can only see **your own**
requests.

### Lifecycle
```
submitted → under_review → (approved | rejected | needs_info)
          → in_progress → (completed | failed)
```

### Endpoints (REST) / tools (MCP)
| REST | MCP tool | Purpose |
| --- | --- | --- |
| `POST /api/agent/v1/requests` `{title, body, category?}` | `submit_change_request` | open a request (`category`: feature\|system\|change\|bug) |
| `GET /api/agent/v1/requests` | `list_my_requests` | list your requests + status |
| `GET /api/agent/v1/requests/{id}` | `get_request` | full detail + conversation thread + the admin's evaluation/decision |
| `POST /api/agent/v1/requests/{id}/messages` `{message}` | `post_request_message` | reply in the thread (e.g. answer a `needs_info`) |
| `POST /api/agent/v1/requests/{id}/feedback` `{results?, issues?, completion_status}` | `post_request_feedback` | report progress; `completion_status` ∈ in_progress\|completed\|failed\|blocked |

Reporting `completed`/`failed` on an `in_progress` request advances it to that
terminal state. Everything is visible to the admin in **/admin → Change Requests**.

---

## 7. Limits & security model

- **Rate limit:** per-token, per-minute (admin-set; default 60/min). `429` + `Retry-After` when exceeded.
- **IP allowlist:** optional per token; non-allowlisted source IPs get `403 ip_not_allowed`.
- **Read-only tokens:** writes return `403 write_disabled`.
- **Revocation:** a revoked token stops working immediately.
- **No raw SQL, no destructive ops** are ever exposed. Reads/writes go through the same validated handlers the operator console uses.

*Questions or a new capability? Open a change request (§6) — that's exactly what it's for.*
