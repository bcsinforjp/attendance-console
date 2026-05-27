# Desktop Agent — Integration Spec (server ⇄ PC `watch.js`)

> **Audience:** the AI/dev that owns the Windows desktop agent (Electron/Node, `watch.js`).
> **Base URL:** **`https://link.genbafms.com`** (recommended). `/api/v1/*` is reachable on **any** genbafms host — `link.genbafms.com`, `genbafms.com`, `www.genbafms.com` — and is gated **only** by your `X-API-Key`; the browser host-login wall does **not** apply to `/api/v1`. If your current base URL already works you may keep it — standardising on `link.genbafms.com` just keeps everything on one domain. (App-update *uploads* are admin-only/server-side; the agent only *downloads*.)
> **Auth:** every `/api/v1/*` call sends `X-API-Key: <APP key>` **and** `X-Agent-Version: <build>` (unchanged). `401 {"detail":"Missing or invalid X-API-Key header."}` = key problem (not host/login); `401 {"detail":"authentication required"}` should no longer occur on `/api/v1`. Treat any non-200 as retry-later.
> **Goal of this update:** make the agent (1) honor a server **pause/stop** switch gracefully and (2) **self-update** from a file the admin publishes in the web console, while (3) reporting its running version so the admin can see it.

This doc is the single source of truth. The server side is already deployed; the **PC agent must be changed to match the items marked ⬚**.

---

## 1. Every request: send the agent version  ⬚

Add this header to **all** `/api/v1/*` requests:

```
X-Agent-Version: <your build string, e.g. 2026.05.19-1>
```

The server records it and shows it in **/admin → Agent → AGENT VERSION**. Keep it stable per build; bump it whenever you apply an update (see §3).

---

## 2. Deactivate → IDLE mode  ⬚

The admin can **deactivate the app** from the web console (/admin → Agent →
**Deactivate app**). This is *not* a short pause-and-retry — when deactivated
the agent must drop into a quiet **IDLE** state until it is **Activated** again.

When deactivated the server does **both**:

| Call | Normal | **When deactivated** |
| --- | --- | --- |
| `GET /api/v1/status/precheck` | `{"action":"upload"\|"skip"\|"confirm_replace"}` (200) | `{"action":"paused","deactivated":true,"reason":"app deactivated by admin — agent should go idle"}` (HTTP 200) |
| `POST /api/v1/pdf/upload` | 200 | **HTTP 423 Locked** |
| `POST /api/v1/xlsx/upload` | 200 | **HTTP 423 Locked** |
| `POST /api/v1/pdf/auto-upload` | 200 | **HTTP 423 Locked** |

> Wire note: the precheck `action` value stays `"paused"` for backward
> compatibility; the authoritative signal is **`deactivated: true`** (also on
> `GET /api/health` → `agent.deactivated`). Treat either as "go idle".

**Required agent behavior — IDLE mode  ⬚:**

1. **Enter IDLE** when precheck returns `deactivated:true` (action `paused`) **or** any upload returns **HTTP 423**:
   - **Stop the file watcher** — do not scan, queue, hash, or process new files.
   - Do **not** upload. Do **not** treat it as an error (no error dialogs, no error-log spam).
   - **Leave every local file exactly where it is** — untouched, not moved to handled/done, not re-ordered.
2. While IDLE, run only a slow **reactivation heartbeat**: call `GET /api/v1/status/precheck` (or `GET /api/health`) about **every 5 minutes** — nothing else. No hot-loop, no retries of pending files.
3. **Exit IDLE (reactivate)** as soon as the heartbeat no longer reports `deactivated` (precheck returns a normal action / `agent.deactivated:false`): restart the file watcher and resume normal operation. Nothing was lost — files were left in place.
4. The 423 is a hard server guarantee — nothing is ingested while deactivated even if the agent ignores the signal. Honoring `deactivated` just keeps the agent silent and idle instead of error-spamming.

Recognised precheck actions:

```
upload          → POST the file
skip            → already have it; move local file to handled
confirm_replace → ask the user; upload only on confirm
paused (deactivated:true) → DEACTIVATED: enter IDLE mode (stop watcher,
                            5-min heartbeat only, files untouched) until reactivated
```

---

## 3. Self-update protocol  ⬚

Admin publishes an update file (any type — `watch.js`, a `.zip`, or an installer) in **/admin → Agent → Desktop app update**. The agent pulls it.

### 3.1 Poll for an update

```
GET /api/v1/app-update
X-API-Key: <APP key>
X-Agent-Version: <current>
→ 200
{
  "available":   true,
  "version":     "2026.05.19-1",
  "filename":    "watch.js",
  "sha256":      "<64 hex>",
  "size":        12345,
  "notes":       "what changed",
  "mandatory":   false,
  "updated_at":  "2026-05-19T12:00:00",
  "download_url":"/api/v1/app-update/download"
}
```

`available:false` (or `version` equal to your running version) → nothing to do.

Poll cadence: once on startup, then every ~30–60 min (or alongside the normal precheck loop).

### 3.2 Decide

- If `available` and `version` ≠ your running `X-Agent-Version` → an update is pending.
- `mandatory:true` → apply as soon as safe (e.g. when idle / not mid-upload). Until applied, you may keep working unless you choose to hard-stop on mandatory.
- `mandatory:false` → apply at next safe idle window.

### 3.3 Download + verify + apply

```
GET /api/v1/app-update/download
X-API-Key: <APP key>
→ 200  (the raw file; Content-Disposition has the filename)
```

1. Download to a temp path.
2. **Verify SHA-256** of the bytes equals `sha256` from §3.1. Mismatch → discard, retry later, do **not** apply.
3. Apply by artifact type:
   - **`watch.js`** → replace the agent script, then restart the agent process.
   - **`.zip`** → unzip into the app dir (atomic: stage → swap), then restart.
   - **installer (`.exe`/`.msi`)** → run it silently per its flags, then it relaunches.
4. After restart, set the new `X-Agent-Version` to the published `version` and resume normal operation. The admin console will then show the new version under AGENT VERSION (confirms the update landed).

### 3.4 Safety

- Never apply while an upload is in flight — finish or abort cleanly first.
- Keep a backup of the previous build so a bad update can be rolled back.
- All update calls are key-protected; treat non-200 as "try again later", never as a reason to stop watching files.

---

## 4. Print → use the server PDF-View page  ⬚

The server already renders **print-ready, correctly-fitted** pages. The agent's
"Print" action must **not** format/scale/print locally or set any printer page
size — it must just **open the right URL**; that page owns page-setup, fit,
pagination and offers **Print** + **Download PDF**.

| Report | URL to open | Page setup (server-controlled) |
| --- | --- | --- |
| Gantt | `https://link.genbafms.com/pdf/gantt?date=YYYY-MM-DD` | **A4 portrait, 4 mm margins**, full-width fit, breaks only between worker rows. (`@page` rule in `gantt.html:299`; content sized to `.page{width:210mm}`.) |
| Summary | `https://link.genbafms.com/pdf/summary?date=YYYY-MM-DD&report=N` | **B3 landscape, 10 mm margins**, full-width fit (`max-width:none` under `@media print`). (`@page` rule in `summary.html:234`.) |

> **Page-size advice for any agent that runs `printToPDF` locally (Electron etc.):** match the dimensions above, **not** what the table said before 2026-05-27 (which incorrectly listed B3 portrait / A3 portrait). Mismatched dimensions produce a wider sheet than the page is designed for, so the 210 mm gantt content sits inside ~50 % blank space. Use `{ width: '210mm', height: '297mm' }` for gantt and `{ width: '515mm', height: '364mm' }` for summary — same as a real Chrome would pick up from the page's own `@page` rule on the manual-print path.

Agent behavior for "Print":

1. Open the URL (with the correct `date`, and `report` for summary) in the
   **user's default browser** (or an embedded webview).
2. The user clicks **Print** (uses the right `@page` size automatically) or
   **Download** (gets the fitted PDF, e.g. `attendance_report_<date>.pdf`).
3. Do **not** apply any local "fit to page" / scaling / printer page-size —
   the server page owns all of it. Overriding re-introduces cut-row / wrong-size.

> **Auth:** `/pdf/*` are **browser pages behind the GenbaLink login** (not
> `/api/v1` key endpoints). This is an open-in-browser, human-clicks-print
> flow — it works when the user is logged in to the dashboard on that host
> (existing `gbl_session` cookie). It is **not** a machine/key endpoint; do
> not call it with `X-API-Key`. Unattended/automated printing is **not**
> supported by this route (would need a separate server change).

---

## 5. Endpoint reference

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/api/v1/status/precheck?type=&date=&sha256=` | X-API-Key | Upload decision (now may return `paused`) |
| POST | `/api/v1/pdf/upload` | X-API-Key | Upload PDF (423 when paused) |
| POST | `/api/v1/xlsx/upload` | X-API-Key | Upload xlsx/xlsm (423 when paused) |
| POST | `/api/v1/pdf/auto-upload` | X-API-Key | Trigger auto-process (423 when paused) |
| GET | `/api/v1/app-update` | X-API-Key | Latest published app build metadata |
| GET | `/api/v1/app-update/download` | X-API-Key | Download the published build file |

Always send `X-API-Key` **and** `X-Agent-Version` on every one of these.

---

## 6. `watch.js` change checklist  ⬚

- [ ] Add `X-Agent-Version` header to every `/api/v1/*` request.
- [ ] Detect deactivation: precheck `deactivated:true` (action `paused`) **or** HTTP **423** **or** `GET /api/health` `agent.deactivated:true`.
- [ ] On deactivation → **enter IDLE mode**: stop the file watcher, no processing, no uploads, leave files untouched, no error state.
- [ ] While IDLE → only a ~5-min reactivation heartbeat (precheck/health); no retries, no hot-loop.
- [ ] On reactivation (no longer deactivated) → restart watcher, resume normally.
- [ ] Add an update poller: `GET /api/v1/app-update` on startup + interval.
- [ ] Implement download + **SHA-256 verify** + apply (per artifact type) + restart.
- [ ] After update, report the new version via `X-Agent-Version`.
- [ ] Persist "last applied update version" locally to avoid re-applying the same build.
- [ ] **Print** action → just open the server PDF-View URL in the browser (§4); no local print formatting / page-size / scaling.

---

## 7. Admin side (already live — for context)

- **/admin → Agent tab**: live status (online / offline / **deactivated-idle**), request log, **Deactivate / Activate app**, **Desktop app update** (publish/clear a file, set version/notes/mandatory; big files via the LAN uploader), AGENT VERSION (what the PC last reported), and a link to this spec.
- Server stores the update file under `attendance_app/app_updates/`; metadata in `app_update.json`. Admin can also fast-register a file already on the Pi (no upload).
- Deactivate flag persists in `admin_config.json` (`ingestion_paused`); survives restarts. When set → precheck `deactivated:true` + uploads HTTP 423 → agent goes IDLE (see §2).

---

## 8. 2026-05-27 server-side changes (informational — no agent code change required)

These changes all landed server-side this week. **None of them break the existing `/api/v1/*` contract.** The agent should keep doing exactly what §1–§7 describe; this section just flags what changed behind the scenes so the agent dev isn't surprised.

### 8.1 Excel files now ingest themselves within 5 hours (no operator click required)

- A systemd `attendance-doctor.timer` (every 5h) scans `auto_uploads/daily_packs/` for stuck `.xlsm` files and runs the full **`auto-extract-excel` → `save-excel-batch`** chain on each. Files then move to `done/`.
- **Agent impact:** none. The agent's upload (POST `/api/v1/xlsx/upload`) is sufficient on its own; you no longer need to remind the user to click "Auto-update" in the Console.
- **Optional improvement** — if you want **immediate** ingestion (don't wait up to 5h), the agent can chain the same two endpoints right after upload:
  1. `POST /api/daily-packs/auto-extract-excel?date=YYYY-MM-DD` → returns preview (does NOT save)
  2. `POST /api/daily-packs/save-excel-batch` with the parsed payload from step 1 → saves to `daily_pack_items`
- The PDF flow (`/api/v1/pdf/auto-upload?save=true`) is unchanged — it's already single-call extract+save.

### 8.2 Real client IP now logged

- Every `/api/v1/*` call previously logged `ip=::1` in `agent_requests.jsonl` because the Cloudflare Tunnel exits onto the Pi's loopback. The server now reads `CF-Connecting-IP` first, so the **real source PC's IP** appears in the log going forward.
- **Agent impact:** none. Just FYI: uploads are now traceable to the originating Windows machine.

### 8.3 New endpoint — `GET /api/daily-packs/{record_date}/history`

- Returns the change history for a date's pack count (BOOTSTRAP / INSERT / UPDATE rows with `old_packs`, `new_packs`, `old_note`, `new_note`, `changed_at`, `changed_by`). Backed by a Postgres trigger on `daily_packs` — catches every code path that writes the table.
- **Auth:** session-gated on GenbaLink hosts (NOT `/api/v1/*` key-protected). The agent generally won't call it directly; it exists for the dashboard + the operator. If the agent ever shows a "verify upload landed" view, this is the right read endpoint to hit from a browser session.

### 8.4 LINE flow (server-side)

- LINE attendance + summary cards now point at `link.genbafms.com/m/report` and `/m/summary` (public mobile viewer, no login, no signed token). Reverted from the brief signed-PDF experiment earlier the same day.
- **Agent impact:** none. The agent does not call LINE.

### 8.5 Base URL recap

- The Cloudflare Tunnel `rnd-pi` routes all of `rnd.asiakawaii.com`, `genbafms.com`, `www.genbafms.com`, `link.genbafms.com`, `api.genbafms.com` to local nginx. Any of these works for `/api/v1/*`. `link.genbafms.com` remains the documented standard.

---

## 9. Why there's no `/api/v1/app-pdf/` (decision log, 2026-05-27)

A spec request landed today proposing a server-side PDF endpoint (`GET /api/v1/app-pdf/gantt`, `GET /api/v1/app-pdf/summary`) so the agent could stop calling `webContents.printToPDF` locally. **Not implemented**, because:

- Chromium-148 + `rpi-chromium-mods` on this Pi renders `about:blank` to PDF fine but **hangs on every network fetch** (tried 127.0.0.1 / localhost / proxy-direct / `--headless=new` / `--single-process` etc.). Curl to the same URL is instant — it's a Pi-OS Chromium issue, not a FastAPI issue.
- Gotenberg-in-Docker would route around the Chromium quirk but adds a long-running daemon on a Pi with only ~387 MB free RAM, which we'd rather not commit to as a first move.
- The agent's real symptom ("narrow content / blank space in the printToPDF output") turned out to be a **page-size mismatch**, not a CSS-container issue: the agent was sending B3 portrait dimensions to a page designed for A4 portrait. Updating the agent's `printToPDF` page-size to match the actual `@page` rule (§4 above) closes the symptom without server-side rendering.

Revisit if (a) the operator needs unattended PDF generation that the agent can't deliver, OR (b) Pi RAM gets a meaningful headroom upgrade. See `AGENT_DEV_REPLY_2026-05-27.md` for the full reply sent back to the agent dev.

---

*If the server contract changes, this file is updated and re-served at `/admin/agent-spec`. Build the PC agent against this document.*
