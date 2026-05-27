# Changelog — V3 Attendance Console

Live log of every change made to the app. Newest on top.
I update this file on every edit so it can drive the project changelog.

Format: `YYYY-MM-DD — [area] what changed (why) → files`

---

2026-05-27 — [spec-decision/docs] **Declined the proposed `/api/v1/app-pdf/{gantt,summary}` server-side PDF endpoint after a feasibility test; fixed the page-size contract in `DESKTOP_AGENT_INTEGRATION.md` that was the actual cause of the agent's printToPDF symptoms.** Agent dev (separate desktop / Electron team) sent a detailed spec request asking the Pi to render `/pdf/gantt` and `/pdf/summary` to PDF on the server. Feasibility:
  - `chromium --headless=new --print-to-pdf=out.pdf about:blank` → works in 1.8 s.
  - Same chromium with `--print-to-pdf=out.pdf http://127.0.0.1:8002/api/health` → hangs to timeout at 30/60/90 s on every flag combination tried (`--single-process`, `--proxy-server=direct://`, `--disable-dev-shm-usage`, `--headless` vs `--headless=new`, 127.0.0.1 vs localhost). curl to the same URL returns instantly — it's a `rpi-chromium-mods` / Chromium-148 quirk specific to Pi-OS, not a FastAPI issue. Combined with ~387 MB free RAM + 2.4 GB swap pressure, decided not to ship server-side rendering right now.
  - **Root-cause discovered while reviewing the spec**: the agent's "narrow content / ~50% blank page" symptom is *not* a CSS container issue. The integration doc was telling the agent **B3 portrait for gantt / A3 portrait for summary**, but the actual `@page` CSS targets **A4 portrait** (`gantt.html:299`) and **B3 landscape** (`summary.html:234`). The agent's `printToPDF` was sending B3 portrait dimensions for the gantt → A4-sized content sat centred on a wider sheet → ~50% blank. Right fix: agent matches `{width:'210mm',height:'297mm'}` for gantt and `{width:'515mm',height:'364mm'}` for summary.
  - **`DESKTOP_AGENT_INTEGRATION.md §4` table corrected** to list the actual `@page` rules + an explicit note about pre-2026-05-27 incorrect values. **Added §9 "Why there's no `/api/v1/app-pdf/`"** as a decision log so future re-discussions have history. Revisit if (a) operator needs unattended PDF generation, OR (b) Pi RAM gets meaningful headroom.
  - **Full reply drafted** in `AGENT_DEV_REPLY_2026-05-27.md` (this is what gets sent back to the agent dev — covers the page-size fix, the feasibility result, all 7 of their §7 questions, and a `printToPDF` page-size snippet they can drop into v2.4.29).
  - → `DESKTOP_AGENT_INTEGRATION.md:130-135` (table fix), `:191-204` (new §9), `AGENT_DEV_REPLY_2026-05-27.md` (new doc). No `main.py` / DB / runtime changes — pure docs + decision log. No PROGRESS_BUG_STATUS entry — this is internal docs, not operator-facing.

2026-05-27 — [docs] **DESKTOP_AGENT_INTEGRATION.md §8 added** — informational change-summary covering all today's server-side fixes (auto-doctor, CF-Connecting-IP, /history endpoint, LINE flow, tunnel-hosts). Explicit "Agent impact: none" against each entry so the agent dev sees at a glance that nothing in `/api/v1/*` broke; the only optional callout is §8.1's "chain extract+save after upload if you want immediate ingestion instead of waiting up to 5h for doctor". → `DESKTOP_AGENT_INTEGRATION.md` (appended; nothing else changed). No PROGRESS_BUG_STATUS entry — this is internal docs, not operator-facing.

2026-05-27 — [audit/observability] **Pack-count change history via Postgres trigger; real client IP captured behind the Cloudflare Tunnel.** Operator asked to back-trace today's pack count and found there's no version log — `daily_packs` is overwrite-only. Also, every Desktop-Agent upload was logging as `ip=::1` because the cloudflared tunnel (named `rnd-pi`) exits onto the Pi's loopback so nginx sees only its own peer.
  - **New `daily_packs_history` table + trigger** in Postgres. Schema: `(id, record_date, action, old_packs, new_packs, old_note, new_note, changed_at, changed_by, source_hint)`. Index on `(record_date, changed_at DESC)`. The trigger `daily_packs_audit_trigger` fires AFTER INSERT/UPDATE on `daily_packs` and calls `trg_daily_packs_audit()`. Catches **every** code path that writes to `daily_packs` without per-call-site instrumentation. Actor attribution via `current_setting('app.actor', true)` — callers can `SET LOCAL app.actor = '...'` to record who made the change; NULL means system/unattributed.
  - **Bootstrap**: a single `BOOTSTRAP` row inserted for every existing `daily_packs` entry (139 rows) at install time so history isn't blank for past data.
  - **New endpoint `GET /api/daily-packs/{record_date}/history?limit=N`** (default 50, max 500). Returns newest-first list with old/new values and notes. Session-gated on GenbaLink hosts (the path doesn't match any GBL_PUBLIC_PREFIXES entry, so the existing cookie wall applies).
  - **Verified end-to-end**: bootstrap row for 2026-05-26 (`new_packs=12049`); after `POST /api/daily-packs` bumping to 12549, then reverting to 12049, the endpoint returned **3 rows** — BOOTSTRAP → UPDATE → UPDATE — with correct `old_packs`/`new_packs` deltas and timestamps.
  - **CF-Connecting-IP capture** for the real client IP. The access-log middleware (line ~638) used to read `X-Real-IP || X-Forwarded-For || request.client.host` — all of which resolved to `::1` because cloudflared connects to nginx via loopback. Added `cf-connecting-ip` as the highest-priority source, falling back to the existing chain. Confirmed live: a test request from a public IPv6 (`2402:6b00:e12e:1f00:c44e:3992:b44a:8101`) now appears correctly in `agent_requests.jsonl` instead of `::1`. The `/lan-upload` endpoint (which intentionally rejects CF traffic) was left untouched.
  - **Important context discovered**: `cloudflared-tunnel.service` (tunnel name `rnd-pi`, PID 1982) routes 5 hostnames — `rnd.asiakawaii.com`, `genbafms.com`, `www.genbafms.com`, `link.genbafms.com`, `api.genbafms.com` — all to local nginx. Config at `/home/pi/.cloudflared/config.yml`. The 5,484 `::1` API-key calls in `agent_requests.jsonl` since 2026-05-19 were all tunneled remote uploads, not local processes. The `APP` key (`app-...`) is presumably used by a Windows PC running `watch.js`; with the new IP capture the operator can correlate against the CF dashboard to identify the source machine.
  - Backups: `main.py.bak.20260527_000000` (post-change snapshot). Database changes (CREATE TABLE / FUNCTION / TRIGGER + bootstrap INSERT) are idempotent — re-running the migration is safe.
  - → `main.py:638-645` (CF-Connecting-IP), `main.py:6763-6802` (new history endpoint), Postgres: `daily_packs_history`, `trg_daily_packs_audit()`, `daily_packs_audit_trigger`.

2026-05-26 — [bugfix/mobile-pages] **`/m/summary` and `/m/report` data section "failed to load" on `link.genbafms.com` — BASE path detection misfired on the bare `/m/*` URL.** Earlier today: opened up the GET-only data APIs (`/api/productivity`, `/api/m/`, `/api/gantt/`, …) so the mobile pages could fetch their data. The endpoints went green, but the pages were STILL showing "failed to load" because the **client-side BASE derivation** in `summary.html` and `gantt.html` was hardcoded for the legacy `/attendance/m/*` path and produced a broken BASE on the bare `/m/*` path. Same class of bug as the [2026-05-15 dashboard fix](#).
  - **`summary.html` line 409-417** — `BASE` derivation. Old regex `/^(\/.*?)\/m\/summary\/?$/` required at least one `/<segment>/` between the start and `/m/summary`, so on `location.pathname = /m/summary` it didn't match and the fallback `p.lastIndexOf("/summary")` returned 2, producing `BASE = "/m"`. Every `api(...)` call then became `/m/api/productivity?...` → **404**. Fix: relax the regex to `/^(.*?)\/m\/summary\/?$/` (allows an empty prefix), return `mMobile[1] || ""`, and add an explicit `/summary` desktop fast-path to keep the desktop case clean. Verified by simulation: `/m/summary` → `BASE=""`, `/attendance/m/summary` → `BASE="/attendance"`, `/summary` → `BASE=""`, `/attendance/summary` → `BASE="/attendance"`.
  - **`gantt.html` line 383-394** — `MOBILE_MODE` AND the `<base>` href injection had the same bug. Old regex `/^\/.*\/m\/(report|summary|gantt)\/?$/` required a non-empty prefix, so on bare `/m/report` mobile mode never activated AND no `<base>` was injected → relative `fetch('api/gantt/...')` resolved to `/m/api/gantt/...` → **404**. Fix: drop the `^\/.*` requirement from the MOBILE_MODE test (just match `/m/(report|summary|gantt)$` anywhere), and relax the base-href regex's prefix group to allow empty (`(.*?)` instead of `(\/.*?)`). The injected `<base>` is `/` when there's no prefix and `/<prefix>/` otherwise — both work because relative `api/X` resolves against the base URL. Verified by simulation: `/m/report` → mobile=True, base=`/`; `/attendance/m/report` → mobile=True, base=`/attendance/`; `/gantt` (desktop) → mobile=False.
  - **No middleware / route changes needed** — the API endpoints opened up earlier today (`/api/productivity`, `/api/m/`, `/api/gantt/`, `/api/members/`, `/api/daily-packs/items/`) already returned 200; the pages just weren't calling the right URLs.
  - Verified: served HTML now contains the new comment markers (`"Mobile path:"` in summary, `"Bare /m/report"` in gantt) and is one block bigger (48280B vs 48012B for summary, 59071B vs 58905B for gantt). `/api/productivity` and `/api/gantt/{date}` both 200 from `link.genbafms.com` with an iPhone Safari UA.
  - Backups: `static/summary.html.bak.20260526_230119`, `static/gantt.html.bak.20260526_230119`.
  - → `static/summary.html:409-419` (BASE derivation), `static/gantt.html:383-396` (MOBILE_MODE + base href injection).

2026-05-26 — [line/auth/revert] **Reverted the signed `/pdf/gantt` LINE flow back to plain `/m/report`; opened up the GET-only data APIs that the mobile pages need on the GBL hosts.** Operator tested the signed-PDF approach and asked for a clean revert: "send M link and no want login password or anything for that" + flagged that the summary report was "not loading data". Two reverts + one fix.
  - **LINE link revert**: `link_url = f"{base}/m/{page}?date={safe_date}"` (where `page = "report" if attendance else "summary"`) restored in BOTH `/api/line/send-mobile-link` (line ~9219) and `/api/line/send-message` (line ~9265). Snapshot upload + branded card thumbnails + button label all unchanged.
  - **Signed-token plumbing removed**: deleted `_get_pdf_link_secret`, `_make_pdf_signed_link`, `_verify_pdf_signed_token`, `_PDF_LINK_SECRET_CACHE`, `_PDF_LINK_PAGES` (above `GBL_PUBLIC_PREFIXES`), and the bypass branch in `genbalink_host_auth`. `admin_config.json:pdf_link_secret` (43-char secret bootstrapped earlier today) also removed.
  - **Mobile-page data fix** — root cause of the "summary not loading data" report. `/m/summary` and `/m/report` HTML pages were already public on GBL hosts (`/m/` in the allow-list), but their JS fetches hit gated `/api/*` paths and got 401. Verified by curl: `/m/summary` returned 200 (HTML loaded) while `/api/m/summary?date=…` returned 401 → page rendered empty. Same class of bug behind `/m/report` ("dayoff blank, daily packs empty"). Fix: added 5 GET-only prefixes to `GBL_PUBLIC_PREFIXES` — `/api/daily-packs/items/`, `/api/gantt/`, `/api/members/`, `/api/productivity`, `/api/m/`. All paths under these prefixes are GETs in the route table; no mutation routes happen to share these prefixes (verified `grep '@app\.(post\|put\|delete)\("/api/(gantt\|members\|productivity\|m)/'` returned empty). The same data was already publicly reachable via the default `rnd.asiakawaii.com` vhost, so this only unifies behavior across hosts. `/api/dayoff/schedule` was **NOT** added because its path has both a GET and a PUT — the mobile page renders without dayoff highlighting in degraded mode rather than expose the mutation.
  - **Verified** after `systemctl restart attendance.service` on `Host: link.genbafms.com`:
    - **Mobile data APIs now reach 200**: `/api/gantt/latest-date`, `/api/gantt/dates-with-data`, `/api/gantt/2026-05-24`, `/api/daily-packs/items/2026-05-24`, `/api/members/list?section=1`, `/api/productivity`, `/api/m/summary?date=2026-05-24&days=30` — all 200.
    - **Regression checks holding**: POST `/api/daily-packs/save-excel-batch` → 401; PUT `/api/dayoff/schedule` → 401; GET `/api/daily-packs/2026-05-24` → 401; GET `/console` → 401.
    - **Signed bypass cleanly removed**: `/pdf/gantt?date=…&exp=…&t=bogus` → 401 (was 200 with valid HMAC before the revert).
  - Backups: `main.py.bak.20260526_225124`, `admin_config.json.bak.20260526_225124`. Earlier same-day backup at `main.py.bak.20260526_224018` captures the in-between signed-PDF state if it's ever needed.
  - → `main.py` (4 deletions: helper block, middleware bypass line, 2× LINE link_url rewrites; 1 addition: 5 new public-prefix entries with explanatory comments), `admin_config.json` (removed `pdf_link_secret`).

2026-05-26 — [line/auth] **LINE Attendance button now opens the signed print-ready PDF page; signed-token bypass added to the host-auth middleware.** Operator: tapping the attendance card from LINE used to load the mobile viewer (`/m/report`), but they want the print-ready B3-portrait page (`/pdf/gantt`) so recipients can Print/Download in one tap. Problem: `/pdf/*` is session-gated on GenbaLink hosts (per the host-auth wall) so a phone recipient with no login session got 401. Fix: HMAC-signed query token that the middleware honors as an alternative to a session cookie.
  - **New helpers in `main.py`** (just before `GBL_PUBLIC_PREFIXES`): `_get_pdf_link_secret()` (lazy bootstrap; persists to `admin_config.json:pdf_link_secret` — `secrets.token_urlsafe(32)` on first call), `_make_pdf_signed_link(base, page, date_str, ttl_days=7)`, `_verify_pdf_signed_token(path, query_params)`. Token = first 32 hex chars of `HMAC-SHA256(secret, f"/pdf/{page}|{date}|{exp}")`. `hmac.compare_digest` for constant-time check.
  - **Middleware bypass** in `genbalink_host_auth`: after the public-prefix check, before the `_gbl_request_user` check, allow through if `path.startswith("/pdf/")` AND `_verify_pdf_signed_token(...)` is True. Other `/pdf/*` requests still require a session.
  - **LINE send updated** in both `/api/line/send-mobile-link` (line ~9217) and `/api/line/send-message` (line ~9265). When `type=attendance`: `link_url = _make_pdf_signed_link(base, "gantt", safe_date, ttl_days=7)`. When `type=summary`: keeps `f"{base}/m/summary?date={safe_date}"` (no change). Snapshot upload + branded card thumbnails + button label all unchanged.
  - **Verified** with `Host: link.genbafms.com` after `systemctl restart attendance.service` (`admin_config.json` now has `pdf_link_secret` of length 43):
    - `signed-valid_gantt`     → **200** (intended path for attendance)
    - `signed-valid_summary`   → **200** (token works for both pages, only gantt is used in the live LINE flow)
    - `tampered_gantt`         → **401**
    - `expired_gantt`          → **401** (exp 1 day in the past)
    - `no-token_gantt`         → **401** (existing behavior preserved)
    - `wrong-date_gantt`       → **401** (token signed for 2026-05-24, request for 2026-05-25)
  - **Security model**: the token authenticates only one specific `(page, date)` combo for 7 days. Sharing the link inside a private chat works as intended; brute-forcing the 128-bit (32 hex chars) signature is infeasible; the signing secret never leaves the Pi. Rotating the secret invalidates all in-flight LINE links — acceptable since LINE messages are read same-day in practice.
  - Backup: `main.py.bak.20260526_224018` (post-change snapshot — the pre-change state is recoverable by reverting the three blocks documented above).
  - → `main.py` (new helpers + middleware bypass + 2× LINE send-flow edits), `admin_config.json:pdf_link_secret` (auto-created on first call).

2026-05-26 — [autodoc/doctor/admin] **Doctor auto-ingest activated; Excel two-step save chained; DB clone-to-SD+USB task added; LINE base URL re-pointed; new AutoDoc admin tab.** Multi-part change so `doctor.py` (the 5h `attendance-doctor.timer` oneshot) actually *resolves* problems it detects, and the admin UI shows what it did.
  - **New `DOC` API key** in `api_keys.json` (mode 0600), wired into `/etc/systemd/system/attendance-doctor.service` as `Environment=ATTENDANCE_DOCTOR_KEY=…`. `daemon-reload` + immediate oneshot validated; the prior `auto_process: disabled (set ATTENDANCE_DOCTOR_AUTO_PROCESS=1 + ATTENDANCE_DOCTOR_KEY)` log line is gone.
  - **`doctor.py` rewrite** (`doctor.py.bak.20260526_220833`):
    - `trigger_ingest` no longer reports "FAILED HTTP 404" for the PDF endpoint when the watched folder only has xlsm files — that 404 is the expected "no PDF files in folder" response and is now logged as `triggered daily_packs_pdf: no matching file (404)`.
    - New `_trigger_excel_chain()` chains `POST /api/daily-packs/auto-extract-excel?date=…` (with the file's encoded date so multi-file folders pick the right one) → `POST /api/daily-packs/save-excel-batch` with the preview payload. Without this chain `auto-extract-excel` only returned a preview — files would never land in `daily_pack_items`. First real run cleared the stuck `夜勤用日報２６．０５．２６.xlsm` (production_date=2026-05-26, 13 products) and `夜勤用日報２６．０５．２４.xlsm` (15 products).
    - New `check_db_clone()` task: when the total row count across the 7 tracked tables differs from the last successful clone, runs `pg_dump | gzip` and writes `attendance_db_<stamp>.sql.gz` to both `/media/pi/sd-root/db_clones/` and `/media/pi/MyData/db_clones/`. Per-target failure is non-fatal (e.g. SD pulled → USB still proceeds; next tick retries the failed target). Retention `CLONE_RETAIN=7` per target. State persisted in `logs/last_db_clone.json`. First clone: 167,214 B → 2 targets.
  - **SD card auto-mounted at `/media/pi/sd-root`** via new `/etc/fstab` UUID entry (`d6944274-f2f7-4644-96a4-213c3b367f5c`, `defaults,nofail,noatime,x-systemd.device-timeout=10s`). The SD partition (`mmcblk0p2`) already contained a Pi OS rootfs from before the NVMe migration — left untouched; only `db_clones/` was added at the root, owned `pi:pi`.
  - **New endpoint `GET /admin/api/doctor-runs?limit=N`** (default 20, max 100). Reads the last 256 KB of `logs/internal_health_logs.log`, splits on `=== doctor run TIMESTAMP ===` markers, parses each run into named sections (`db_health`, `registry_consistency`, `sidecar_configs`, `unprocessed_files`, `ingest_trigger`, `db_clone`, `routine_events`), classifies each line's severity (`ok` / `warn` / `err`), and rolls up an `overall_status` per run. Response also surfaces `next_run` from `systemctl list-timers attendance-doctor.timer` and the most recent `last_clone` from `last_db_clone.json`. Auth: `_require_admin_session()` (same as other `/admin/api/*` endpoints). → `main.py:4983-5093`.
  - **New AutoDoc tab** in `static/admin.html`: tab button (line 174), `<section id="panel-autodoc">` (lines 636-664), `showTab` wiring (line 704), `refreshAutodoc()` JS renderer (lines 1425-1525). Newest run defaults expanded; per-section status pills (✓ / ! / ✗) and per-line color coding (green = OK / auto-fixed, orange = WARN, red = FAILED) highlight what doctor auto-solved or what failed. Header shows log path, file size, next-run hint, and a "last clone" pill.
  - **LINE base URL re-pointed** `https://rnd.asiakawaii.com/attendance` → `https://link.genbafms.com` in `line_config.json`. The old domain stopped routing to the Pi after the GenbaLink rollback (`rnd.asiakawaii.com/m/report` → nginx 404; `link.genbafms.com/m/report` → 200). `_line_load()` re-reads on every send, so this is hot — no restart needed. Backup: `line_config.json.bak.20260526_221433`.
  - Verified end-to-end: post-rewrite doctor run at 22:09:52 shows `ingest_trigger: 2× extract+save OK`, `db_clone: 167KB → 2 targets`, and `done_files daily_packs archived=42` (was 41). `/admin/api/doctor-runs?limit=2` returns 2 runs (the latest `ok`, the prior `err` because of the old 404 line — historical).
  - Backups: `doctor.py.bak.20260526_220833`, `static/admin.html.bak.20260526_221643`, `line_config.json.bak.20260526_221433`. Service unit edited in-place under `/etc/systemd/system/`.
  - → `doctor.py` (full rewrite), `main.py:4983-5093` (new endpoint), `static/admin.html:174,636-664,688,704,1425-1525`, `api_keys.json` (added `DOC`), `line_config.json:public_base_url`, `/etc/systemd/system/attendance-doctor.service`, `/etc/fstab`.

2026-05-24 — [auth/desktop-agent] **Unblocked `link.genbafms.com` as the single base URL for the desktop agent and the dashboard verify endpoint.** Three documented browser-facing endpoints were returning `401 authentication required` on the GenbaLink hosts because they weren't in the host-auth exempt list — only `/api/v1` was. Symptoms: `/api/data-status/...` 401-spammed the journal every ~15 s from dashboard polling without a session; the desktop agent's `daily_packs_pdf` / `daily_packs_xlsx` Auto-update IPC handlers (API_APP_GUIDE.md §4.3) silently failed on `link.genbafms.com`; the §3 / §6.5 curl recipes only worked via `rnd.asiakawaii.com/attendance`. Fix: added two prefix entries to `GBL_PUBLIC_PREFIXES` — `/api/data-status/` and `/api/daily-packs/auto-extract` (the latter's `startswith` match covers both `/auto-extract` PDF and `/auto-extract-excel` Excel triggers). No security regression: the same endpoints are already publicly reachable on the default `rnd.asiakawaii.com` vhost with zero auth — this just unifies behavior across hosts. The wall still gates `/console`, `/api/daily-packs/save-excel-batch`, `/api/daily-packs/{record_date}` GET, and every other non-listed `/api/*` path behind a `gbl_session` cookie. → `main.py:769-773`.
  - Verified on `Host: link.genbafms.com` after `systemctl restart attendance.service`:
    - **Flipped to working:** `GET /api/data-status/2026-05-24` → 200; `POST /api/daily-packs/auto-extract-excel` → 200/404 (404 = no files in watched folder, domain-correct); `POST /api/daily-packs/auto-extract` → 200/404 (same).
    - **Regression checks passing:** `GET /api/v1/ping` w/ APP key → 200; `GET /api/v1/pdf/list` w/o key → 401 `Missing or invalid X-API-Key`; `POST /api/daily-packs/save-excel-batch` w/o session → 401 `authentication required`; `GET /api/daily-packs/2026-05-24` w/o session → 401; `GET /console` w/o session → 302 → `/login`.
  - Also removed the dead `fetch("/api/daily-packs/extract-excel-recompute")` call in `static/console.html` `recomputePrediction()`. The endpoint never existed (the next line's own comment said so) and the result was never read — it just spammed the server with 405s on every Excel-tab start-time change. The client-side recompute below is unchanged. → `static/console.html:1714-1715` (was 1715-1716).
  - Backups: `main.py.bak.094604`, `static/console.html.bak.094604`.

2026-05-15 — [bugfix/dashboard] **Dashboard widgets stuck on "loading" when served via `genbafms.com/dashboard`.** Root cause: `dashboard.html` line 284 derived BASE from the first path segment via `pathname.match(/^(\/[^/]+)/)`. On `/attendance/dashboard` that returned `/attendance` (correct, since nginx/FastAPI strip it), but on the bare `/dashboard` path served by the genbafms vhost it returned `/dashboard` — every API call then fired at `/dashboard/api/dashboard/snapshot` and 404'd. Replaced with an explicit check: `BASE = pathname.startsWith("/attendance/") ? "/attendance" : ""`. The genbafms dashboard page now correctly hits `/api/dashboard/snapshot` / `/api/dashboard/weather`, and the legacy `/attendance/*` mount is unchanged. Users may need a hard refresh to pick up the new HTML.
  - Verified with a real `gbl_session` cookie on `Host: www.genbafms.com`: `/dashboard` 200, `/api/dashboard/snapshot` 200, `/api/dashboard/weather` 200. `rnd.asiakawaii.com/attendance/api/dashboard/snapshot` still 200.
  - → `static/dashboard.html:284-287`.

2026-05-15 — [routing/landing] **Public landing page split into a standalone static site at `/var/www/genbafms/`, served by nginx at `link.genbafms.com`.** Two-step change today; this entry replaces the earlier same-day entry.
  - **New folder `/var/www/genbafms/`** with `index.html` (the landing page) — single card matching `login.html`'s palette (dark navy gradient, teal/indigo brand), brand "V3 Attendance Console", tagline + one "Sign in →" button → `/login`. No JS, no form, no auth. This is now a separate "site" from the FastAPI app, owned by nginx.
  - **nginx vhost `/etc/nginx/sites-available/genbafms`** rewritten: `server_name` now includes `link.genbafms.com` alongside the existing apex/www. `location = /` does `try_files /index.html =404` against the new `root /var/www/genbafms`. Every other path (`/login`, `/dashboard`, `/console`, `/reports`, `/api/*`, `/static/*`, `/m/*`, …) keeps proxying to FastAPI 8002. Old vhost backed up to `genbafms.bak.20260515`.
  - **`main.py`**: added `link.genbafms.com` to `GBL_AUTH_HOSTS` so the host-gated auth middleware fires on the new subdomain too. Reverted the earlier same-day root-handler / `/`-allowlist edits — they're no longer needed (nginx serves `/` directly, never reaches FastAPI). The file is back to the pre-landing-page state except for the `GBL_AUTH_HOSTS` line.
  - **Why `link.genbafms.com`**: `www.genbafms.com` is 301-redirected to `rnd.asiakawaii.com/attendance/console` at the Cloudflare edge and we can't easily flip that today. `link.*` is a fresh subdomain the user can route to the Pi via Cloudflare Tunnel for testing.
  - **DNS / Cloudflare (DONE 2026-05-15):** Cloudflare DNS for `genbafms.com` zone was re-pointed from Squarespace (4× A records) to the `rnd-pi` tunnel. `www.genbafms.com` CNAME changed from `ext-sq.squarespace.com` to the tunnel. New CNAME `link.genbafms.com` → tunnel. Cloudflared local `config.yml` updated to include `link.genbafms.com` in the ingress list (backup: `config.yml.bak.20260515`); `cloudflared-tunnel.service` restarted clean. Public verification: `https://genbafms.com/`, `https://www.genbafms.com/`, `https://link.genbafms.com/` all return the landing page with HTTP 200 over Cloudflare HTTPS.
  - Verified locally (LAN, with `Host:` header):
    - `link.genbafms.com /` → static landing (`<title>V3 Attendance Console</title>` + Sign-in button)
    - `link.genbafms.com /login` → 200 (proxied)
    - `link.genbafms.com /dashboard` → 302 → `/login?next=/dashboard` (auth gate intact)
    - `link.genbafms.com /api/health` → 200 JSON healthy
    - `www.genbafms.com /` on LAN → static landing (Cloudflare 301 only blocks the public path)
    - `rnd.asiakawaii.com /attendance/console` → 200 (no regression)
  - Backups: `main.py.bak.20260515` and `/etc/nginx/sites-available/genbafms.bak.20260515`.
  - → `/var/www/genbafms/index.html` (NEW), `/etc/nginx/sites-available/genbafms` (rewritten), `main.py:310` (`GBL_AUTH_HOSTS`).

---

2026-05-14 — [branding/filesystem] **Rolled back the May 13 "GenbaLink" brand text + folder rename.** User-facing rename was reverted; auth subsystem kept intact.
  - **Brand text revert**: every user-visible "GenbaLink" → "V3 Attendance Console" across `main.py` (FastAPI title), `static/site_header.js` (brand div), `static/login.html` (title, logo "GL"→"V3", name), and page titles in `console.html`, `reports.html`, `dashboard.html`, `summary.html`, `gantt.html`, `management.html`. The "GenbaLink Users" panel heading in `management.html` is now "Users". Page titles match the pre-rebrand backup at `/var/www/backups/attendance_app_v4.0_20260506_072719/`.
  - **Kept**: v4.1 auth subsystem (`/api/auth/*` endpoints, `users.json`, host-gated middleware, login page, Users panel) is fully functional. Internal code-level strings (Python docstrings, `GBL_AUTH_HOSTS`, `genbalink_host_auth` function name, JSON `_note` field, JS comments, HTML cache-buster `?v=20260513-genbalink`) were left alone because they are not user-visible.
  - **Filesystem**: `/var/www/genbalink/` renamed back to `/var/www/attendance_app/` (now a real folder, no more symlink). `/var/www/genbalink-next/` dev copy deleted. systemd `attendance.service` (which references `/var/www/attendance_app`) resolves to the real folder directly now; no unit edit needed.
  - **Untouched**: nginx vhost `/etc/nginx/sites-available/genbafms` and Cloudflare Tunnel config `/home/pi/.cloudflared/config.yml` were not modified — the `genbafms.com` domain still routes to port 8002 and the host-gated auth still gates that domain. If the domain itself is to be retired, those need a separate pass.
  - Verified: `/api/health` → 200 healthy; `/console`, `/dashboard` → 200; served HTML shows `<title>V3 Attendance Console · Operations Workflow</title>`.
  - → `main.py:40`, `static/site_header.js:204`, `static/login.html:6,75,76`, `static/console.html:6`, `static/reports.html:6`, `static/dashboard.html:6`, `static/summary.html:6`, `static/gantt.html:6`, `static/management.html:6,1313`. No new `.bak` files created (changes are surgical line-level edits; existing `.bak` files retained as historical snapshots).

---

2026-05-13 — [auth/branding] **GenbaLink rebrand + new domain `genbafms.com` + multi-user login** (Phase 1 of 3).
  - **Brand display rename**: every user-visible "V3 Attendance Console" / "IMMS" → "**GenbaLink**". `app = FastAPI(title="GenbaLink", version="4.1")`. Page titles updated across all 6 pages. Brand text in `site_header.js` is now "GenbaLink". URL paths, file paths, systemd service, DB are **all unchanged** — zero broken links.
  - **Multi-user auth** (PBKDF2-SHA256, 200k iters, stdlib only — no bcrypt dep): `users.json` (mode 0600) seeded with `admin` / `admin2026`. New endpoints under `/api/auth/`: `login`, `logout`, `whoami`, `users` (CRUD, admin-only), `change-password`. In-memory session store with 12-hr TTL, cookie name `gbl_session` (HttpOnly, SameSite=Lax, path=/). Login page at `/login` with GenbaLink branding.
  - **Host-gated middleware**: `genbalink_host_auth` runs ONLY for requests with `Host: genbafms.com` (or `www.genbafms.com`). All existing `/attendance/*` access via the default vhost is **untouched** — office bookmarks keep working without login. Public allow-list inside the gated host: `/login`, `/logout`, `/api/auth/*`, `/api/health`, `/api/announcement`, `/api/line/*` (LINE webhooks), `/m/*` (mobile reports linked from LINE buttons), `/static/*`, `/admin` (legacy admin keeps its own password). HTML navigation gets `302 → /login?next=…`; AJAX/API gets `401 JSON`.
  - **User management UI** added to Setup page (`management.html`) — only renders when `host=genbafms.com`. Lets admins list/create/delete users + lets any user change their own password.
  - **Site header** (`site_header.js`) shows current logged-in user as a pill (`👤 admin ★ ↪`) with click-to-logout, only when `/api/auth/whoami` returns authenticated.
  - **Nginx**: new vhost `/etc/nginx/sites-available/genbafms` (symlinked to sites-enabled). Listens on port 80 for `genbafms.com` + `www.genbafms.com`, proxies to `127.0.0.1:8002` at root path. Existing default vhost (`/attendance/`) untouched.
  - Verified: `/attendance/*` → 200 (open), `genbafms.com/dashboard` (no cookie + Accept: text/html) → 302 to `/login?next=/dashboard`, login → cookie set → page serves, logout → cookie cleared → page redirects again. Wrong password → 401.
  - **Phase 2 (URL path rename)** and **Phase 3 (directory move)** intentionally deferred — see `PROGRESS_BUG_STATUS.md` for status.
  - → `main.py` (auth subsystem ~250 lines, host middleware ~40 lines), `static/login.html` (new), `static/site_header.js` (brand + user pill), `static/management.html` (Users panel, only via genbafms.com), all 6 page titles, `/etc/nginx/sites-available/genbafms` (new), `users.json` (new, 0600). Backups: `main.py.bak6`, `site_header.js.bak2`, `management.html.bak.preauth`, `/etc/nginx/ai-server.bak.preauth`.

2026-05-13 — [dashboard] **Pro-level visual upgrade** for the Status dashboard.
  Layout (top→bottom):
  - **Hero KPI band** (4 large tiles with inline sparklines + delta pills): Today's Packs · vs Plan · Productivity · Workers Present.
  - **Weather strip** (compact, gradient cards, 3-day forecast).
  - **2-column row** — left: Production Plan with per-line progress bars + collapsible item tables; right: **Donut chart** for N/Y section split + per-section productivity rows with delta pills.
  - **30-day area chart** for daily packs (gradient fill, grid lines, hover tooltips, axis labels).
  - **30-day multi-line chart** for productivity (per section + combined, three colored series, legend).
  Visuals: dark theme with teal/indigo accent palette, Inter + JetBrains Mono fonts, soft radial-gradient background, glass-morphism cards, hover lift on KPI tiles, fade-in animations, skeleton loaders during fetch, semantic delta colors (green up / red down / amber neutral). All charts are inline SVG — no chart library, no extra dependencies.
  Backend extension: `/api/dashboard/snapshot` now returns `last_30_days` (was `last_7_days`) with per-day `packs`, `n_packs`, `y_packs`, `sec1_hours`, `sec2_hours`, `total_hours`, computed `lp` (combined) and `lp_sec1` / `lp_sec2`. Hours come from a single SQL query against `attendance_records` + `temp_staff` (no per-day _gantt_compute_for_date round-trips). → `main.py` (snapshot endpoint), `static/dashboard.html` (full rewrite, ~600 lines)

2026-05-13 — [dashboard] **New live Status dashboard** at `/dashboard` (replaces the placeholder page).
  Five cards top-to-bottom:
  1. **🌤 This Week's Weather** — wttr.in for `${DASHBOARD_WEATHER_LOC:-Yamanashi}`, 3-day forecast with avg/max/min °C, condition, humidity, rain %, wind. 30-min server-side cache; degrades gracefully if API unreachable (shows last good cache or empty card, never blocks page).
  2. **📋 Today's Production Plan** — `production_plan` rows grouped by `line_code` (A/B/C). Each line collapsible with item rows showing planned qty, PPH target, takt time. Bottom totals row shows Total Planned vs Actual today (% of plan).
  3. **📦 Today's Pack Count** — total + per-section (N=製造１課, Y=製造２課) tile cards with progress bars vs plan.
  4. **📈 Last 7 Days — Daily Packs** — inline SVG bar chart (no chart library). Each bar has hover-tooltip with date + pack count.
  5. **⚡ Productivity** — per-section + combined p/h, hours, present/total headcount, with ▲/▼ delta vs previous day.
  Date picker at the top to anchor the dashboard to any date (defaults to latest `daily_packs.record_date`).
  Backend: two new endpoints — `GET /api/dashboard/snapshot?date=YYYY-MM-DD` (single round-trip aggregating plan + today + 7-day + productivity, reuses `_gantt_compute_for_date` so numbers match the Gantt page exactly) and `GET /api/dashboard/weather` (cached wttr.in proxy via `urllib` stdlib, no extra dependency). → `main.py` (new section ~line 2718), `static/dashboard.html` (full rewrite from placeholder)

2026-05-13 — [nav] **Top nav collapsed from 6 tabs to 4** with clearer names + emoji prefixes:
  Old: `🌐 Dashboard · Console · Gantt · Summary · Reports · Management`
  New: `📊 Status · 📋 Reports · ⚙️ Setup · 📥 Intake`
  - Gantt + Summary still live at their existing URLs (`/gantt`, `/summary`, `/m/report`, `/m/gantt`, `/m/summary`) — bookmarks unchanged. Visiting either page now highlights the **Reports** tab. Entry to Gantt / Summary is via the Reports page's existing Attendance Report + Summarizing Report cards.
  - `Console` → renamed `Intake` (signals "data IN", complements Reports' "data OUT").
  - `Management` → renamed `Setup` (broader, future-proofs for non-roster settings).
  - `Dashboard` → renamed `Status`.
  - All routes/URLs preserved; only labels + emoji changed. → `static/site_header.js` (single source of truth for the topnav), `static/reports.html` (one stale "Management" link → "⚙️ Setup"), `static/dashboard.html` (placeholder text updated)

2026-05-13 — [sections] **Cross-section ghost placements**: a code can now appear in multiple sections in `sections.json` — `*` placements become "Disabled" ghost rows in that section while a non-`*` placement (anywhere) becomes the employee's real active home. Example: `00007009*` in section 1 + `00007009` in section 2 → ghost shown at section 1 position 17, real worker shown at section 2 position 65 with actual clock-in/out. Ghosts are excluded from productivity (`staff_total`, hours, p/h) regardless of section. All-muted codes (no non-`*` appearance anywhere) keep their ghost in the section they were placed. Each section's display order respects per-section position, so user-edited order is preserved exactly. Refactor: new `_build_section_indexes()` returns `(SECTION_OF_CODE, MUTED_CODES, ACTIVE_CODES, MUTED_PLACEMENTS, SECTION_POSITIONS)`; deprecated `section_order_index_map()` and the `order_index` parameter on `_gantt_compute_for_date` (replaced by per-section `SECTION_POSITIONS`). → `main.py` (helpers, `iter_codes_in_section_order`, `refresh_management_data`, `_gantt_compute_for_date`, gantt entry caller)

2026-05-13 — [gantt] Muted (`*`-marked) employees are **never flagged "🚨 Unauthorized"** even when the operator's "Highlight unauthorized absence" toggle is ON. They render as a calm gray "Disabled" pill instead. Frontend-only change; the backend already attaches `muted: true` to those rows. → `static/gantt.html` (absent-row branch in the Gantt renderer)

2026-05-12 — [sections] **`*` mute marker** for sections.json codes. Append `*` to any code (e.g. `"00007007*"`) to mark an employee as **display-only / no-hours**: they remain visible in their section row (ID + name) but IN/OUT/working-hours render blank (`--:--`), the row is **excluded from productivity calculations** (staff_total, hours, p/h denominators), and Excel export cells for that employee are blank. The muted employee is **always injected** into their section's Gantt list, even on days they have no DB attendance record. Use cases: long-term leave, unpaid suspension, contract paused. Backend: `clean_code()`, `MUTED_CODES`, `is_muted_code()` helpers; `apply_employee_roster` / `_gantt_compute_for_date` honour the marker; `management_save_roster` re-applies existing `*` markers on save so the management UI never silently strips them. → `main.py`, `sections.json` (test mark on `00007007*` for verification)

2026-05-12 — [roster/sections] sections.json is now the single source of truth for both **section assignment** and **display order**. Previously roster order drove every output; now the position of each `code` inside `sections.json` determines Gantt row order, Excel export order, members list order, and management UI order. employee_roster.json is now a name-only registry — the management UI still saves name edits but no longer reorders it. Codes in sections.json without a roster entry render as `???` placeholder; codes in roster but absent from sections.json fall into the `Unassigned` bucket. Backups: `*.bak` of main.py, sections.json, employee_roster.json, static/management.html. → `main.py` (helpers `name_for_code` / `iter_codes_in_section_order` / `section_order_index_map`; `apply_employee_roster`, `_gantt_compute_for_date` + caller, `management_payload_from_files`, `management_save_roster`, `members_list`, gantt docstring)

---

## v4.0 — Stable Release (2026-05-06)

Cumulative roll-up of every change since v3.5. Tagged `v4.0` on `dev` and
pushed to origin. From this version onward, the desktop agent + report
date math + internal health check are all in their stable shape.

Highlights since v3.5:

- **Pre-upload protocol replaced by a single decision endpoint.** The two
  legacy probes (`/api/v1/status/check` + `/api/v1/status/check-sha`) are gone;
  desktop now calls `GET /api/v1/status/precheck?type=&date=&sha256=` and gets
  back one of `upload | skip | confirm_replace`. The endpoint reconciles
  `uploaded_file_registry` against the data tables on every call, so a manual
  `DELETE FROM attendance_records` no longer leaves the registry lying. See
  [DESKTOP_AGENT_TASK.md](DESKTOP_AGENT_TASK.md).
- **Plan A: `/gantt?date=` is the report date end-to-end.** Attendance and
  temp_staff queries fetch at `record_date − 1`; daily_packs at `record_date`.
  One URL, one page, both halves of the day visible together. See §1 of
  [DATE_RULES.md](DATE_RULES.md).
- **Internal health check (`doctor.py`) running on a 5-hour systemd timer.**
  Row counts every table, finds orphan registry rows, validates sidecar JSONs,
  drains pending files in watched folders. Output appended to
  `logs/internal_health_logs.log`. Install instructions in [systemd/INSTALL.md](systemd/INSTALL.md).
- **Date rules consolidated in `date_service.py` with full reference doc.**
  PDF date / shift / production / report / pack — all derived from one anchor
  with constants you can change in one place. See [DATE_RULES.md](DATE_RULES.md).
- **Cross-app database documentation.** All 7 tables, every column, every
  sidecar JSON, every filesystem path, every env var, with worked examples.
  See [/var/www/DATABASES.md](../DATABASES.md).
- **Roster / sections / batch-upload polish** carried in from in-flight
  work (`employee_roster.json`, `sections.json`, `upload_latest.bat`,
  `API_APP_GUIDE.md`).

Known issues left open in v4.0:

- Auto-extract path doesn't transition `uploaded_file_registry.status` from
  `received` → `loaded`. Data lands in tables correctly, but registry stays
  stale. Self-heals on next precheck call; doctor.py also flags it. Tracked
  for v4.0.x patch.

Backup of the v4.0 source tree (excluding venv) lives at
`/var/www/backups/attendance_app_v4.0_<timestamp>/`.

---

## 2026-05-06 — Plan A: gantt URL date is the report date

The `/gantt?date=YYYY-MM-DD` URL is now interpreted as the **report (= production) date**
end-to-end. Background: the desktop team uploaded `就業日報2026.04.07.pdf` +
`夜勤用日報２６．０４．０８.xlsm` (one logical day of work, two calendar dates per
DATE_RULES.md). Old code queried `attendance_records` and `daily_packs` with the same
URL value, so the two halves could never appear on one page. Plan A reads the URL as
the report date, queries `daily_packs` at it directly, and queries
`attendance_records` + `temp_staff` at `report_date − 1` (the shift date).

- **[api]** `_gantt_compute_for_date` now pulls attendance/temp_staff with
  `WHERE record_date = (%s::date - 1)` while daily_packs stays `= %s`.
  → `attendance_app/main.py:2208-2243`
- **[api]** `/api/gantt/latest-date` returns `GREATEST(MAX(attendance.record_date) + 1,
  MAX(daily_packs.record_date))` so the picker default is the most recent **report**
  day (not the most recent shift day).
  → `attendance_app/main.py:2149-2168`
- **[api]** `/api/gantt/dates-with-data` returns report dates by `UNION`-ing
  `attendance_records.record_date + 1` with `daily_packs.record_date`.
  → `attendance_app/main.py:2170-2196`
- **[verify]** `GET /api/gantt/2026-04-08` now returns `total_packs=11434` (4/8
  daily_packs) + 93 attendance rows + temp_staff 10 ppl / 90h (4/7) — both halves
  on the same response.
- **[backup]** `main.py.bak_20260506_planA` saved before the edit.
- **[no change needed]** Frontend (`gantt.html`) already shows
  `Attendance Report｜${url_date}` and `シフト ${url_date − 1}（曜日）`, which
  matches Plan A.
- **[separate small bug, not fixed in this commit]** When ingestion succeeds via
  the auto-extract path, `uploaded_file_registry.status` stays at `received` instead
  of flipping to `loaded` (and `loaded_at` / `record_count` stay NULL). The data
  IS in the tables, but the registry lies. Flagged for a follow-up commit —
  doctor.py's `registry_consistency` check will catch it and the
  `/api/v1/status/precheck` endpoint already self-heals on the next probe.

→ `attendance_app/main.py`, `attendance_app/CHANGELOG.md`

## 2026-05-06 — Single precheck endpoint + doctor.py periodic health check

Replaced the two-call dance (`/api/v1/status/check` + `/api/v1/status/check-sha`)
with one decision endpoint and added a 5-hourly self-healing health check.
Background: a manual `DELETE FROM attendance_records` left
`uploaded_file_registry` claiming the data was still loaded, so the desktop
agent's SHA probe kept returning `exists:true` and refused to re-upload.
Fix is to make the data table the source of truth and reconcile the registry
on every probe; doctor.py catches any stale rows that slip through and also
drains files that landed in the watched folder but never reached `done/`.

- **[api]** New `GET /api/v1/status/precheck?type=&date=&sha256=` returning one
  of `{"action":"upload"|"skip"|"confirm_replace", "reason":...}`. Logic:
  probe the data table by `type`; if empty, `DELETE FROM uploaded_file_registry
  WHERE target_date=date OR sha256=sha` then return `upload`; if data exists,
  registry hit on (sha,date) → `skip`, miss/diff → `confirm_replace`.
  → `attendance_app/main.py` (replaces lines previously holding `/check` and
  `/check-sha`)
- **[api breaking]** Removed `GET /api/v1/status/check` and
  `GET /api/v1/status/check-sha`. Desktop agent must switch to `/precheck`.
  → `attendance_app/main.py`, `attendance_app/DESKTOP_AGENT_TASK.md`
- **[ops]** New `attendance_app/doctor.py` standalone script: row-counts every
  table, finds orphan registry rows (status=loaded but data row count=0),
  validates sidecar JSON configs, lists files sitting in watched folders that
  never reached `done/`, optionally hits `/api/attendance/auto-upload` and
  `/api/daily-packs/auto-extract*` to drain them. Append-only log at
  `logs/internal_health_logs.log`. Exit 0 always (watcher, not a gate).
  → `attendance_app/doctor.py`
- **[ops]** Systemd unit + 5h timer (`OnUnitActiveSec=5h`) under
  `attendance_app/systemd/`. Install: `sudo cp` the two files into
  `/etc/systemd/system/` and `systemctl enable --now attendance-doctor.timer`.
  See `attendance_app/systemd/INSTALL.md`.
  → `attendance_app/systemd/{attendance-doctor.service,attendance-doctor.timer,INSTALL.md}`
- **[docs]** `/var/www/DATABASES.md` gains §4 (precheck contract) and §5
  (doctor responsibilities + log location). `DESKTOP_AGENT_TASK.md` rewritten
  to single-call flow, with a new acceptance test for the manual-DELETE
  self-heal case.
- **[backup]** `main.py.bak_20260506_precheck` saved before the endpoint swap.
- **[deploy reminder]** `sudo systemctl restart attendance.service` is required
  for the new endpoint to go live (uvicorn doesn't hot-reload).

→ `attendance_app/main.py`, `attendance_app/doctor.py`,
   `attendance_app/systemd/*`, `attendance_app/DESKTOP_AGENT_TASK.md`,
   `/var/www/DATABASES.md`

## 2026-05-05 — Activate pre-upload routes (BACKEND_FIX_REQUEST resolution)

Desktop team reported HTTP 404 on `/api/v1/status/check` and `/api/v1/status/check-sha`
through `https://rnd.asiakawaii.com/attendance/...`. Cause: `attendance.service`
had not been restarted since the route additions earlier today, so the running
uvicorn (started 2026-05-04 09:09) was serving the pre-edit code.

- **[ops]** `sudo systemctl restart attendance.service`. New start
  2026-05-05 20:20:12. Route count in live `/openapi.json` jumped to 105 incl.
  the two new `status/check*` paths. → no code change.
- **[verify]** All three §5 acceptance curls in `BACKEND_FIX_REQUEST.md` now
  return HTTP 200 with `{"exists":false,…}` through the public URL, including
  the real-world SHA from the desktop log
  (`076514…7757`). → no code change.
- **[note — separate, NOT acted on]** Audit of port 8003 found a stale
  `uvicorn main:app` (PID 553808, started 2026-04-25) running an older
  snapshot of `attendance_app/main.py` (only 6 routes). It is squatting on
  the port that `upload.service` is configured to bind. **This is unrelated
  to today's desktop fix** (nginx routes `/attendance/` to 8002, not 8003)
  but should be cleaned up — flagged for a follow-up decision from the owner.

→ no files changed (operational restart only)

## 2026-05-05 — Pre-upload status check + SHA-256 dedup registry

Backend-side support for the desktop agent's `API_CHECK_SPEC.md` (Section 1
of that doc). Two layered protections so the same file is never processed
twice and a date that already has rows is never silently overwritten.

- **[db]** New table `uploaded_file_registry`: `(sha256 UNIQUE, file_type,
  file_name, file_size, target_date, record_count, received_at, loaded_at,
  moved_path, source_key, status)`. Indexes on `(file_type, target_date)`
  and `status`. Created idempotently from `init_db()`. → `main.py`
- **[helpers]** `_sha256_hex`, `_registry_lookup_sha`,
  `_registry_record_received`, `_registry_mark_loaded`, `_parse_iso_date_or_400`.
  All single-purpose, all reuse the existing `get_db_connection()` pool. The
  existing flat `_move_to_done(src, kind)` from 2026-05-02 is kept as-is —
  no YYYY-MM nesting, no signature change, no collision. → `main.py`
- **[api]** New `GET /api/v1/status/check?type={attendance|production}&date=YYYY-MM-DD`
  per the original `API_CHECK_SPEC.md`. Always 200 (or 400/401) so the desktop
  client's fail-open contract holds. attendance → reads `attendance_records`,
  production → reads `daily_packs` first then falls back to
  `daily_pack_items`. Response carries `records` (attendance) or `pack_count`
  (production) plus `uploaded_at`. → `main.py`
- **[api]** New `GET /api/v1/status/check-sha?sha256=<64-hex>`. Byte-exact
  dedup probe so the desktop agent can skip the network upload entirely
  when the same file has already been processed. Returns full registry
  metadata (status, target_date, moved_path, record_count) on hit. → `main.py`
- **[api]** `POST /api/v1/pdf/upload` and `POST /api/v1/xlsx/upload` now
  SHA-256 the bytes server-side. On hit the request is **rejected with 409
  Conflict** carrying the existing registry row in `detail.registry`. Desktop
  client must treat 409 as terminal (no retry). On miss, file is saved as
  before and a `received` row is inserted into the registry. Success
  responses gained a `sha256` field. → `main.py`
- **[hand-off]** `DESKTOP_AGENT_TASK.md`: full integration spec for the
  desktop AI agent that owns `watch.js`. Includes endpoint contracts, the
  pre-check decision flow, a 5 s probe budget, the 409 branch, and a 5-row
  acceptance-test matrix. → `attendance_app/DESKTOP_AGENT_TASK.md`
- **[ops]** Backup of pre-change `main.py` saved as
  `main.py.bak_20260505_133723` so the change is fully reversible.

→ `main.py`, `DESKTOP_AGENT_TASK.md`

## 2026-05-02 — Retrievable move-to-done warnings (key-protected)

The move-to-done step that runs after a successful DB save is best-effort —
filesystem errors there must never roll back the just-committed save. Until
now those warnings only went to stdout, where the desktop client couldn't see
them. Now they are also persisted to a log file and exposed over an API.

- **[api]** New `GET /api/v1/done-files/warnings` (key-protected, X-API-Key).
  Query params: `limit` (1..2000, default 200) and optional `kind` filter
  (`attendance` | `daily_packs`). Returns `{path, exists, count, warnings:[{ts, kind, filename, src_path, error}, …]}`. → `main.py`
- **[helpers]** New `_log_done_warning()` helper appends one JSON line per
  failure to `attendance_app/logs/done_warnings.log`. The append itself is
  best-effort: a logging failure is swallowed (printed once to stdout) so the
  DB save is never compromised by a logger I/O issue. → `main.py`
- **[behavior]** `_move_to_done()` still returns `None` on failure (response
  carries `moved_to_done: false` as before) and additionally writes the
  warning to disk. No change to success path. → `main.py`
- **[docs]** API_APP_GUIDE: new §6.6 with response shape, `kind`/`limit`
  query params, and recommended desktop-client polling pattern. → `API_APP_GUIDE.md`

→ `main.py`, `API_APP_GUIDE.md`

## 2026-05-02 — Done folder + Restore/Delete in Management

After a successful DB save, the source file used by the import (PDF or Excel)
is moved into a per-kind `done/` subfolder so the next Auto-update doesn't
re-pick it. The Management → 🗑 Data Cleanup tab grew a new "✅ Processed
Files (Done)" card that lists those files and exposes ↩ Restore / 🗑 Delete.

- **[api]** `attendance_auto_upload(save=True)` now moves the picked PDF into
  `<watched-folder>/done/` after the DB save succeeds. Best-effort: any move
  failure is logged and swallowed so the just-committed save is never rolled
  back. Response gains `moved_to_done` (bool) and `done_path` (string|null). → `main.py`
- **[api]** `POST /api/daily-packs/save-excel-batch` does the same after its
  commit, looking up the source by basename in the daily-packs watched folder.
  Response gains `moved_to_done` and `done_path`. → `main.py`
- **[api]** Three new browser-facing endpoints (no API key):
  - `GET  /api/done-files/list` — `{attendance: {path, files[]}, daily_packs: {path, files[]}}` with `{filename, size, modified, extracted_date}` per file.
  - `POST /api/done-files/restore` — `{kind, filename}` → moves the file back to the parent watched folder so the next Auto-update picks it up again.
  - `POST /api/done-files/delete`  — `{kind, filename}` → unlinks the file. Two-step confirm lives in the UI; no soft-delete on the server side.
  Both mutating endpoints validate `kind ∈ {attendance, daily_packs}` and
  reject any path-traversal attempt (`filename` must be a plain basename
  whose resolved path stays inside the Done folder). → `main.py`
- **[helpers]** New `_done_dir_for()`, `_parent_dir_for()`, `_move_to_done()`,
  `_list_done_files()`, `_validate_done_kind()`, `_safe_done_path()`. Done
  folders are auto-created lazily — no manual mkdir step needed. → `main.py`
- **[ui]** Management → 🗑 Data Cleanup tab gains a green "✅ Processed Files
  (Done)" card after the existing "📦 Old uploaded files" section. Two-column
  layout (Attendance / Daily Packs). Each row shows filename, parsed date,
  size, modified time + ↩ Restore / 🗑 Delete buttons. Both actions confirm
  before firing. Loads on first tab open and on Refresh click. → `static/management.html`
- **[safety]** Existing iteration helpers (`_pick_latest_*`, `_pick_*_for_date`, `v1_pdf_list`, `v1_xlsx_list`) already filter on `is_file()` so the new Done subfolders are naturally excluded — no list endpoint surfaces them as pending work.

→ `main.py`, `static/management.html`

## 2026-05-02 — Back-fill any date with files already on the server

Desktop client (`watch.js`) needs to fix a missing day even when the local
file on the office PC is gone but the file is still sitting in the server's
watched folder from a previous upload. To support this:

- **[api]** `POST /api/v1/pdf/auto-upload` accepts a new optional
  `?date=YYYY-MM-DD` query parameter. Without it, behaves exactly as before
  (picks latest PDF — fully backward-compatible). With it, picks the PDF whose
  filename encodes that date and ingests only that file. → `main.py`
- **[api]** `POST /api/daily-packs/auto-extract-excel` gains the same
  `?date=YYYY-MM-DD` optional parameter with identical semantics. → `main.py`
- **[api]** Both endpoints return a structured 404 when the requested date
  has no matching file: `{detail: {error:"file_not_available", kind, requested_date, watched_folder, message}}` — desktop client can now render
  "PDF for 2026-04-23 is not on the server, please upload first" instead of
  guessing from a free-text 404. → `main.py`
- **[api]** New `GET /api/v1/xlsx/list` (key-protected) — companion to the
  existing `/api/v1/pdf/list`. Returns every Excel in the daily-packs watched
  folder with `extracted_date` parsed from the filename so the desktop client
  can decide whether the date is already on the server before deciding to
  upload again. → `main.py`
- **[helpers]** Added `_pick_pdf_for_date()` and `_pick_xlsx_for_date()` next
  to the existing `_pick_latest_*` helpers. Both reuse `_extract_date_from_filename` (NFKC-normalized, full-width digits already supported). → `main.py`
- **[docs]** API_APP_GUIDE: new §6.5 "Desktop-client update guide — back-fill
  any date (v3.4)" with a decision tree, drop-in `watch.js` patch, and a
  copy-paste smoke test for back-filling 2026-04-23. List/retrieve §3 also
  documents `/api/v1/xlsx/list` and the `?date=` parameter. → `API_APP_GUIDE.md`

→ `main.py`, `API_APP_GUIDE.md`

## 2026-05-01 — v3.5 release tag

Bump `app.version` 3.4 → 3.5. Coherent batch shipped on top of v3.4:

- **Daily Packs Excel parser overhaul.** Three new sub-parsers read the right-side **Ｎ合計 / Ｙ合計** off `入力画面`, the **フルキャスト 5 名 / 3 名** rows on `人時生産性` (start time from col C, leave time from col D, total seconds from col E — fixes a column-misread bug), and the **A / B / C lines** on `製造予定表　ＮＹ`. All three blocks saved on Confirm & Save in one transaction.
- **Schema migration.** New `production_plan` table; new `n_total` / `y_total` / `section_start_time` columns on `daily_packs`.
- **Date-keying corrected.** Memory file `project_date_rules.md` captures the four-way relationship (Report = Excel prod = PDF + 1; フルキャスト shift = prod − 1). The Excel save now writes `temp_staff.record_date = production_date − 1` so the gantt overlay and the manual fullcast tab read the right day.
- **Excel preview cleanup.** Dropped Input by / Weather / Total qty fields. Cross-check pill no longer false-alarms when per-product 全合計 is blank. Start time = latest first-item start across A / B / C (= 19:20 either way). End time gets a +30 min buffer.
- **🗑 Data Cleanup tab in Management.** Per-date deletion across 5 date-keyed tables, hard 5-date cap, two-step confirm, no "delete all" mode.
- **Manual フルキャスト tab.** Two new buttons: **⚡ Auto-update from Excel** (drives the whole Daily Packs Excel flow and lands back on the fullcast tab on shift_date) and **Skip →**.
- **Post-save navigation.** Daily Packs Excel direct save → `/reports?date=production_date`. ⚡ Auto-update from fullcast → stays on fullcast tab on shift_date. Reports page reads `?date=` from URL.

Detailed per-feature entries follow below.

→ `main.py`, `README.md`, `PROJECT_INSIDE_AI_BLUEPRINT.md`

## 2026-05-01 — Site-wide announcement banner + Admin API Status tab

- **[ui]** Announcement banner consolidated into `site_header.js`: the same banner driven by `GET /api/announcement` (and edited from `/admin#/announcement`) now renders on **every** full page (Console, Gantt, Summary, Reports, Management, Dashboard) directly under the unified topbar — previously it only showed on Console. Per-browser dismiss is preserved (a "show notice" pill returns it). Hidden on mobile viewers / `?report=1` popups / print. → `static/site_header.js`
- **[ui/cleanup]** Removed the page-local copy of the announcement markup + script from `console.html` and the static `BETA Test period ends 2026-04-30` strip from `management.html` so the banner only renders once. → `static/console.html`, `static/management.html`
- **[admin]** New **Admin → API Status** tab: live view of every `/api/*` and `/admin/api/*` request captured by the access middleware. Top KPI strip (total / 4xx / 5xx / avg / p50 / p95 / endpoint count). Endpoint roll-up table (path, hits, 4xx, 5xx, avg ms, max ms, last status, last seen). Recent requests table colour-coded by status. Path filter + optional 5-second auto-refresh. Backed by new `GET /admin/api/api-status` (admin-session-gated). → `main.py`, `static/admin.html`
- **[admin/copy]** Announcement editor description updated to say "drives the site-wide banner shown on every /attendance/* page" instead of just /console. → `static/admin.html`
- **[verify]** `curl /admin/api/api-status` → 401 (gated, correct). `curl /api/announcement` → 200. site_header.js syntax OK. Cache-bust bumped to `?v=2026050104` on all 6 HTML pages. → live test.

## 2026-05-01 — Feedback FAB rendering fix: defensive inline `display:none`

- **[bug/ui]** Fixed: the feedback modal markup was rendering as visible inline content at the bottom of pages — the FAB worked but the modal contents leaked into the page flow. Root cause: the modal relied solely on a CSS rule in `bannerCss` to be hidden; in the broken state `display:none` wasn't being applied. Made it defensive — the modal element now ships with inline `style="display:none;"` so it is hidden regardless of CSS load order or any external override, and the `.show` class flips it open with `!important`. Cache-bust bumped `?v=2026050102` → `?v=2026050103` on all 6 HTML pages so Cloudflare/browsers pick up the fixed script. → `static/site_header.js`, `static/{console,dashboard,gantt,summary,reports,management}.html`

## 2026-05-01 — Feedback flow polished: floating action button + reader tab in Management
- **[ui]** The "Send feedback" button **moved off the demo banner** into a **floating action button (FAB)** at the bottom-right of every full page (hidden on mobile viewers / report popups / print, same rules as the banner). The FAB is a green pill with a 💬 icon + "Feedback" label; on screens ≤540 px it collapses to just the icon. Hover lifts it slightly with a deeper shadow. The amber demo banner stays under the top nav as a passive notice. → `static/site_header.js`
- **[ui]** **Polished feedback modal**: added a sticky header with title + close (✕) button; bigger card (540 px max width); larger inputs with green focus ring; per-field uppercase eyebrow labels; **live character counter** (`N / 4000`, turns amber at 3,000+, red at 3,900+); a `📍 /current/page/path` line so the operator sees which page the message is being sent from. **Ctrl/⌘ + Enter** sends from inside the textarea. Backdrop blurs slightly; close on Esc / outside-click / ✕. → `static/site_header.js`
- **[ui/admin]** New **Management → 💬 Feedback · ご意見** tab (5th tab, next to 🗑 Data Cleanup). Read-only viewer of the feedback log. Threshold input (1..500, default 50), Refresh button, and a card-per-entry list showing: name (or *anonymous*), UTC timestamp, page path, IP, full multiline message. Calls `GET /api/feedback/recent` server-side; no DB hit. → `static/management.html`
- **[verify]** Live: `GET /api/feedback/recent?limit=5` returns the existing test entry; FAB click on any full page (Console / Gantt / Summary / Reports / Management / Dashboard) opens the polished modal; Management → 💬 Feedback tab renders the entry as a card. → live test.
- **[ops]** Round-15 backups (`*.bak15`) of `site_header.js` and `management.html` taken before edits.

## 2026-05-01 — Data Cleanup tab: From/To range pickers (per-date deletion + Old-uploaded-files sweep)
- **[ui]** Per-date deletion section gained an alternative input mode: From + To date pickers and a **`+ Add range`** button. Clicking expands the inclusive `[from..to]` window into individual dates and merges them into the existing chip selection (deduped, capped at the same 31-date max). Out-of-range / inverted ranges are caught with explicit alerts. The single-date `+ Add to list` button is still there for one-off picks. → `static/management.html`
- **[ui+backend]** Old-uploaded-files retention sweep also accepts an optional **From / To** range:
  - **UI** — two new date inputs next to the days threshold; when set, the scan filters files to those whose `extracted_date` is in the range, drops the threshold check, and recomputes `safe_to_delete = data_in_db`. The status pill includes the range (`… · range 2026-04-15 → 2026-04-22 · 1 safe to delete`). The delete confirmation message becomes `Delete every file in range … → … …` so the operator knows exactly what scope is about to be applied.
  - **Server** — `GET /api/cleanup/old-files` and `POST /api/cleanup/old-files/delete` both accept new optional `range_from` / `range_to` parameters (or body fields). When set: `_apply_range_filter` keeps only files inside the range and recomputes `safe_to_delete = data_in_db`; the days threshold is ignored. Invalid dates / inverted ranges return 400. → `main.py`, `static/management.html`
- **[verify]** Live: `GET /api/cleanup/old-files?range_from=2026-04-15&range_to=2026-04-22` returned `attendance: 1` (the only attendance file with a date in that window — `就業日報2026.04.18.pdf`, `safe_to_delete: true` because the DB has rows). Inverted range (`2026-04-05 → 2026-04-01`) and malformed dates both correctly return 400. → live test.

## 2026-05-01 — Demo-preview banner + feedback flow appended to logs/feedback.txt
- **[backend]** New `POST /api/feedback` body `{message, name?, page?}` validates message presence + 4 KB cap, writes one NDJSON line per submission to `logs/feedback.txt` (auto-creates the directory). Each entry carries timestamp, client IP, user-agent, the page path the message was sent from, optional name, and the message itself. Atomic-write under `_FEEDBACK_LOCK`. → `main.py`
- **[backend]** New `GET /api/feedback/recent?limit=N` (1..500) returns the last N entries newest-first as JSON. Useful for an admin viewer; meanwhile any operator can `tail -f /var/www/attendance_app/logs/feedback.txt` for live tailing. → `main.py`
- **[ui]** `static/site_header.js` extended to inject:
  1. A thin amber **🚧 Demo preview** banner directly below the unified header on every page, with bilingual copy: *"This is a demo preview — your feedback is valuable and helps us improve. / これはデモ版です。ご意見・ご要望はぜひ送信してください。"*
  2. A green **💬 Send feedback** button at the right end of the banner.
  3. A modal that opens on click — name (optional, max 60 chars), message textarea (max 4000 chars), Send / Cancel. Inline status line shows `sending… / ✅ Thanks! / Send error: …`. Escape closes; click outside the card closes.
- The banner is hidden on `body.mobile` (mobile viewer) and `body.report-mode` (report popups) and on print so the focused views stay clean. → `static/site_header.js`
- **[verify]** Round-trip live: `POST /api/feedback {"message":"test from operator"}` → `{"ok": true, "stored_at": "2026-05-01T07:52:14Z", "log_path": "/var/www/attendance_app/logs/feedback.txt"}`. `GET /api/feedback/recent?limit=5` returned the entry. File content is one NDJSON line per submission. → live test.

## 2026-05-01 — Branded LINE card thumbnails + data-status API + 31-day cleanup cap + USER_GUIDE.md
- **[ui/line]** LINE Buttons-Template card now uses operator-supplied **branded thumbnails** instead of the per-day numbers snapshot. The static images live at `static/line_card_default/attendance_card.jpg` and `summary_card.jpg`. The per-day snapshot is still saved to `static/line_images/<type>_<date>.<ext>` as an audit record (and surfaced on the save response as `snapshot_url`) but no longer appears in chat. Memory file `feedback_line_flow_locked.md` updated to record this is the operator-approved final state — **don't go back to using the snapshot as the thumbnail without explicit permission**. → `main.py`, `feedback_line_flow_locked.md`
- **[backend/api]** New `GET /api/data-status/<YYYY-MM-DD>` returns a single-glance health check across every date-keyed data source for that report date. Honours the date-rules memory: attendance + temp_staff lookups go to `shift_date = date − 1`, daily_packs / pack_items / production_plan go to `date`. Response shape: `{report_date, shift_date, all_present, missing[], blocks: {attendance, daily_packs, fullcast, production_plan}}` where each block carries `keyed_on`, `lookup_date`, row counts, and `present`. Use case: a future "📋 Verify before sending" UI pill, or a precondition check inside any report-generation flow. → `main.py`
- **[backend]** `_CLEANUP_MAX_DATES` raised from `5` to `31` per operator request (demo / testing window — covers a full month per request). The matching frontend constant `CLEANUP_MAX_DATES` and the bilingual help copy on Management → 🗑 Data Cleanup were updated to match (`0 / 31 dates selected`, `1 回の操作で 最大 31 日付（1 ヶ月）まで`). The "no delete-all mode" rule and the consent-checkbox safety rail are unchanged. → `main.py`, `static/management.html`
- **[docs]** New top-level `USER_GUIDE.md` (~360 lines) — covers every operator-visible feature in one place: the four-date relationship, top nav, daily workflow, manual fullcast, Reports → LINE flow, mobile viewers, four management tabs (Roster / Day-off / LINE Recipients / Cleanup), data-status endpoint, the desktop `.bat` client, an 8-row troubleshooting cheatsheet, and a "where to look for what" file index. Bilingual snippets where it counts. → `USER_GUIDE.md`
- **[verify]** Live: `GET /api/data-status/2026-04-19` → `all_present: true` (156 attendance / 1 daily_packs summary + 16 items / 2 fullcast / 17 plan rows). `GET /api/data-status/2026-04-29` → `all_present: false, missing: ["attendance","fullcast"]` (only daily_packs + plan, no shift-date attendance or temp_staff). Cleanup cap: 31 dates passes (200), 32 rejects (`too many dates: maximum 31 per request (got 32)`). → live test.

## 2026-05-01 — Gantt page Send-to-LINE button rewired: now uses the card flow (was: PDF + plain-text URL)
- **[ui/bug-fix]** The `💬 Send PDF to LINE` button on `/gantt` was still calling the old `/api/line/upload-and-send` endpoint — it generated a real PDF via `html2pdf.js` and sent a plain-text message with a PDF link. That bypassed the new card flow entirely, so messages from the gantt page didn't match the Summary card style.
- The handler now: (1) loads `html2canvas`, (2) captures the productivity 4-box (`#summary`) on the gantt page as a PNG, (3) posts it to `POST /api/line/send-mobile-link` with `type=attendance`. The server sends one Buttons Template card per recipient → image + title + tap button → `/attendance/m/report?date=…`. Identical card to what the Summary page sends, just with the attendance link.
- Button label changed from `💬 Send PDF to LINE` to `💬 Send to LINE` to reflect the new behaviour. → `static/gantt.html`

## 2026-05-01 — Attendance LINE card link reverted: same shape as Summary (/m/report) — un-revert
- **[backend/un-revert]** Reverted the previous "attendance → /gantt?report=1" change. Both card types now use the symmetric `/m/<page>?date=YYYY-MM-DD` pattern: attendance → `/m/report?date=…`, summary → `/m/summary?date=…`. Operator wants both cards to open the trimmed mobile viewer pages so neither shows admin buttons / PDF prompts. Card layout (image + title + body + tap button), button label, alt text — all unchanged. → `main.py`

## 2026-05-01 — Attendance LINE card links to full /gantt?date=…&report=1 instead of /m/report
- **[backend]** `POST /api/line/send-mobile-link` for `type="attendance"` now builds `link_url = "{base}/gantt?date={date}&report=1"` instead of `{base}/m/report?date={date}`. The `?report=1` flag is honoured by `site_header.js` (added during the toolbar refactor) — it skips the unified header injection so the popup view is focused on the gantt content while keeping the in-page toolbar (date picker, legend) untouched.
- **[backend]** `type="summary"` link is unchanged — still goes to `/m/summary?date={date}` (the rotation-aware mobile chart viewer the operator confirmed works well).
- The card thumbnail, title, body, and `📊 View Report` / `📈 View Summary` button labels are unchanged. Only the URL behind the button changed for the attendance flow. → `main.py`

## 2026-05-01 — LINE send back to Buttons Template card (link hidden behind tap button) — un-revert
- **[backend/un-revert]** The earlier same-day revert (image + plain-text URL) was rolled back at the operator's request. `POST /api/line/send-mobile-link` again sends a **single Buttons Template card** per recipient: snapshot image as the thumbnail, `prefix + date` body, single tap button labelled `📊 View Report` / `📈 View Summary` whose URI = `/m/report?date=…` or `/m/summary?date=…`. `defaultAction` makes the whole card tappable. The raw URL is **not** rendered as plain text in the chat — that's the desired behaviour (clean card, no long URL line).
- Response shape returns to `card_status` per recipient. Helper unchanged. `image_url` and `link_url` are still in the response body for the console UI's success toast / log. → `main.py`
- **[note]** `_line_push` and `_line_push_image` remain available — a future flow can use them if a different message style is needed.

## 2026-05-01 — Reverted LINE send to image + plain-text link (was: Buttons Template card, hid the URL)
- **[backend/revert]** `POST /api/line/send-mobile-link` now sends **two separate messages** per recipient — an `image` message (the 4-box snapshot) followed by a `text` message containing the mobile-viewer URL — instead of a single Buttons Template card. Reason: the card layout hid the URL behind a button label and the operator wants the `/attendance/m/report?date=…` / `/attendance/m/summary?date=…` link to be visible as plain text in the chat thread.
- The text body is the original three-line format:
  ```
  📋 勤怠記録 / Attendance Report
  📅 2026-04-19
  👉 https://rnd.asiakawaii.com/attendance/m/report?date=2026-04-19
  ```
- Response shape unchanged structurally — each recipient now reports both `image_status` and `text_status` (not a single `card_status`). `ok` is true only when both messages reached LINE successfully. → `main.py`
- **[note]** `_line_push_button_template` helper is left in place (unused by `send-mobile-link` now) so a future flow can opt into card output without adding new code. The old card behaviour can be restored by swapping the two `_line_push_*` calls back for one `_line_push_button_template`. → `main.py`

## 2026-05-01 — File retention: one-file-per-day on upload + 30-day retention sweep gated on DB-data presence
- **[backend]** New helpers in `main.py`:
  - `_extract_date_from_filename(name)` — pulls `YYYY-MM-DD` (or `YY.MM.DD`) out of an arbitrary filename. NFKC-folds first so full-width digits like `２６.０４.２９` parse the same as `26.04.29`. Two-digit years interpret as 2000s.
  - `_delete_same_date_older_files(folder, keep, target_date)` — walks the folder and removes every file (except the just-uploaded one) whose extracted date matches `target_date`. Tolerates OS errors so a stale handle doesn't fail the upload.
  - `_db_has_data_for_date(d, kind)` — cheap DB-presence check used by the retention sweep so we never delete a file whose data hasn't actually been ingested yet. `kind = "attendance"` checks `attendance_records`; `kind = "daily_packs"` checks `daily_pack_items` ∪ `daily_packs`.
  - `_scan_old_files(folder, kind, days)` — returns each file with its extracted date, byte size, `is_older_than_threshold`, `data_in_db`, and `safe_to_delete = (old AND in_db)`. Files with no parseable date fall back to the file's mtime so nothing slips through. → `main.py`
- **[backend/upload]** Both `POST /api/v1/pdf/upload` and `POST /api/v1/xlsx/upload` now apply the **one-file-per-day** rule: after a successful save, any other file in the same target folder whose filename encodes the same date is removed. The response gained `extracted_date` and `removed_same_date_files: [...]` so the desktop client can confirm the cleanup landed. Verified: uploading a 2nd `.xlsx` named `2026-04-19_v2.xlsx` to the daily-packs folder deleted the existing `夜勤用日報２６．０４．１９.xlsm` (same parsed date 2026-04-19). → `main.py`
- **[backend/retention]** New endpoints under `/api/cleanup/`:
  - `GET /api/cleanup/old-files?days=N` (1..365, default 30) — returns both watched folders' file lists annotated with `extracted_date / size / is_older_than_threshold / data_in_db / safe_to_delete`. Files with no DB row for their date stay `safe_to_delete: false` regardless of age — operators don't lose unprocessed input.
  - `POST /api/cleanup/old-files/delete` body `{confirm: true, days?: N}` — re-runs the safety check server-side (so a stale UI list can't trick the server) and deletes every file flagged `safe_to_delete=true`. Returns per-folder `deleted[]` and `skipped[]` arrays with reasons. → `main.py`
- **[ui]** New "📦 Old uploaded files · 古いアップロードファイル" section inside Management → 🗑 Data Cleanup tab. Operator picks a threshold (default 30 days), clicks **🔍 Scan**, sees two side-by-side lists (attendance + daily_packs) where each file shows its extracted date and a tag — `🗑 safe to delete` (red, will be removed), `⚠ old but no DB data — kept` (amber), or just `kept` (gray). Single big red **🗑 Delete safe-to-delete files** button at the bottom; double-confirm via browser `confirm()` because the action removes filesystem state. → `static/management.html`
- **[verify]** Live results against the production folders:
  - `GET /api/cleanup/old-files?days=30` returned 12 attendance files + 17 daily_packs files; correctly flagged `就業日報2026.04.01.pdf` (older than 30 days + DB has rows) as the **only** safe-to-delete file. `就業日報2026.04.10.pdf` and `夜勤用日報２６．０４．１１.xlsm` (no DB data) stayed kept.
  - `days=999` rejected with 400 (max 365); `POST … /delete` without `confirm: true` rejected with 400.
  - One-file-per-day round trip (xlsx): same-date upload → `removed_same_date_files: ["夜勤用日報２６．０４．１９.xlsm"]` ✓. → live test.

## 2026-05-01 — Post-save navigation: Daily Packs Excel save → /reports; フルキャスト ⚡ Auto-update → stays on fullcast tab
- **[ui]** Save handler in `console.html` now routes the post-save destination based on which button started the flow:
  - **Daily Packs → Excel segment → Confirm & Save batch →** → `window.location.href = api("/reports") + "?date=" + production_date`. This is the operator's normal end-of-shift workflow: finish Excel input → review the day's report.
  - **2 フルキャスト tab → ⚡ Auto-update from Excel** → returns to the fullcast tab on `shift_date` (= production_date − 1), reloads `temp_staff` for that day so the saved 会社/人数 rows are visible.
  - The destination is controlled by `xlsxState.postSaveGoal` (default `"reports"`); the fullcast ⚡ handler sets it to `"fullcast"` right before clicking the hidden Save button, then it auto-resets to `"reports"` so the next direct save goes back to the default.
  → `static/console.html`
- **[ui]** Reports page (`/reports`) now reads `?date=YYYY-MM-DD` from the URL on load and seeds `$reportDate.value` with it (showing `source: opened from console save (production date)` in the hint). Falls through to the existing latest-DB-date heuristic when no `?date` is passed. → `static/reports.html`
- **[ui]** Daily Packs **Manual** Confirm & Save also now carries the production date forward (`api("/reports") + "?date=" + $packDate.value`). Previously it redirected to `/reports` without a date so the page defaulted to the latest DB date. → `static/console.html`
- **[verify]** Tested both paths in the browser:
  - Daily Packs Excel direct save: `/reports?date=2026-04-19` opens with the report-date input pre-filled to 2026-04-19 and the date-source hint reading "opened from console save (production date)".
  - フルキャスト ⚡ Auto-update: returns to TAB 2 on shift date 2026-04-18, 会社/人数 list shows the just-saved 5 名 / 3 名 buckets. → live test.

## 2026-05-01 — Management → 🗑 Data Cleanup tab: per-date deletion with hard 5-date cap, two-step confirm, NO "delete all" mode
- **[backend]** New endpoints under `/api/cleanup/`:
  - `GET /api/cleanup/preview?dates=YYYY-MM-DD,…` — returns row counts per (table, date) for the requested dates across `attendance_records / daily_packs / daily_pack_items / temp_staff / production_plan`. Dates are validated by regex, deduped, sorted; **maximum 5 dates per request** (returns 400 otherwise). Used to drive the confirmation UI.
  - `POST /api/cleanup/delete` — body `{dates: [...], confirm: true}`. Deletes every row whose date column is in the requested list, across the same 5 tables, in one transaction. Refuses without `confirm: true` (so a stray POST can't wipe data). Returns per-table delete counts + grand total + UTC timestamp.
  - Both endpoints share `_parse_cleanup_dates()` which enforces the cap, the YYYY-MM-DD regex, and dedup.
  - **Deliberate design choice**: there is no "delete all" / "wipe table" mode. The cap of 5 is the operator's safety rail.
  → `main.py`
- **[ui]** New 4th Management tab **`🗑 Data Cleanup · データ削除`** (next to Roster / Day-off / LINE Recipients). Tab itself is highlighted with a soft red border so the destructive area is visible at a glance. Workflow:
  1. **Pick dates** — date input + **+ Add to list** button. Selected dates appear as removable red chips. Live counter shows `N / 5 dates selected`.
  2. **🔍 Preview rows to delete** — fetches the preview API and renders a table per (table, date) with row counts (`0` rows are gray, non-zero are red-bold). Summary line shows total rows that would be deleted.
  3. **Big red warning panel** — only renders when there's something to delete. Bilingual EN+JP "DESTRUCTIVE ACTION · 取り消しできません" warning, plus a checkbox `I understand and want to delete the data shown above. / 上記のデータを削除することに同意します。` that is **the only thing** that enables the red **🗑 Delete data** button.
  4. **Final delete** — POSTs with `confirm: true`. On success the UI shows a green result panel with per-table delete counts, clears the selection, and resets the workflow.
  → `static/management.html`
- **[verify]** Live: `GET /api/cleanup/preview?dates=2026-04-29,2026-04-19` returned `grand_total: 146` rows (attendance_records=80, daily_packs=2, daily_pack_items=30, temp_staff=2, production_plan=32). Safety rails verified — 6-date request returns 400, bad date format returns 400, POST without `confirm: true` returns 400. → live test.
- **[ops]** No DB schema change; this is purely add-only API + UI on top of the existing date-keyed tables. Round-9 backups created (`*.bak9`) before edits.

## 2026-05-01 — フルキャスト start/leave times read from the right Excel cells (was reading the duration column as start time)
- **[backend/critical-bug]** The `_parse_fullcast_rows_from_jisei_sheet` parser was reading `人時生産性` column **C** as `total_seconds`. Wrong — column C is the **start_time** stored as a timedelta-since-midnight (Excel renders it as `19:00`). The actual total worked time lives in column **E**, and the **leave_time** is in column **D**. The bug caused saved `temp_staff` rows to have:
  - `start_time = section_start_time` (= 19:20 from production plan, not 19:00 from the workbook)
  - `leave_time = "10:00"` hardcoded fallback (not 04:00 / 05:00 from D)
  - `total_hours = 19.0` for every bucket (the start-time-as-duration mistake), which made `hours_per_person = 19h` for the 1-headcount case.
- **[backend/fix]** Reworked the parser to read each fullcast row as: **A=headcount, C=start_time (timedelta→HH:MM), D=leave_time (datetime→HH:MM), E=total_seconds (timedelta)**. Adds a tolerant `_hhmm_from_cell()` helper that handles `timedelta`, `datetime.time`, and `datetime.datetime` (Excel's 1900-base) uniformly. Returns `start_time`, `leave_time`, `leave_next_day`, `total_seconds`, `total_hours`, `hours_per_person` per bucket. Heuristic: if `leave_next_day` isn't already set from col E being ≥1 day, infer it from `leave HH:MM ≤ start HH:MM`. → `main.py`
- **[backend/fix]** `save-excel-batch` now uses each parsed row's own `start_time` and `leave_time` instead of falling back to the production-plan section start. Adds a fallback chain when the parser couldn't extract the total: derive from `(leave - start) × headcount` so older workbooks that don't fill column E still save sensibly. → `main.py`
- **[ui]** The `xlsxFullcastDetail` line in the Excel preview now shows the per-row time window: `製造2課: 5 名 · 19:00 → 翌 04:00 (9h/人)`. Operators can verify the times match the workbook before clicking Save. → `static/console.html`
- **[verify]** Round-trip on `2026-04-19` Excel:
  - Parser: `[{5 名, start 19:00, leave 04:00, total 45h, 9h/人}, {3 名, start 19:00, leave 05:00, total 30h, 10h/人}]` — exactly matches the operator's screenshot.
  - SQL: `temp_staff(2026-04-18)`:
    ```
    id 345 | 2026-04-18 | 5 | 19:00 | 04:00 | next-day | 9.00 h/p | 45.00 h
    id 346 | 2026-04-18 | 3 | 19:00 | 05:00 | next-day | 10.00 h/p | 30.00 h
    ```
  - Total labor for the shift: 75h (was being saved as 38h with the bug). → live test.

## 2026-05-01 — Date relationships locked in: フルキャスト row date fixed (now shift_date = production_date − 1) + Skip / Auto-update buttons on the manual fullcast tab
- **[backend/critical-bug]** Fixed a date-keying bug introduced in the morning's Excel-import work. The save-excel-batch endpoint was writing `temp_staff.record_date = production_date` — but `temp_staff` is keyed on **shift date** (= production_date − 1). Every other consumer (`/api/temp-staff/{date}`, the gantt overlay, the manual fullcast tab) reads by shift date, so the Excel-saved フルキャスト rows were landing on the wrong day and not visible from the manual tab. Fix: server computes `shift_date = pdate - timedelta(days=1)` and uses it for both the `DELETE` (overwrite) and the `INSERT`. Save response now includes `shift_date` so the frontend can navigate to the right day. → `main.py`
- **[ui]** Post-save navigation now opens the フルキャスト tab on `shift_date` (server-returned) instead of `production_date`. The success toast shows both dates: `Saved batch for 2026-04-19. Opening フルキャスト on shift date 2026-04-18…`. → `static/console.html`
- **[ui]** **Two new buttons on the manual フルキャスト tab** (TAB 2):
  - **`⚡ Auto-update from Excel`** (accent-colored) — runs the entire Daily Packs Excel auto-extract + save flow from inside the fullcast tab. Implementation: programmatically `switchTab("packs")`, click the Excel segment switch, click `btnXlsxAuRun`, poll until `btnSaveXlsxBatch` becomes enabled (30s timeout), then click Save. The save handler already navigates back to the fullcast tab on the right shift_date — one click does the whole loop end-to-end.
  - **`Skip →`** (muted) — operator confirms there are no フルキャスト for this shift; jumps straight to the Daily Packs tab without writing anything to `temp_staff`.
  → `static/console.html`
- **[memory]** Saved `project_date_rules.md` to the memory store + an entry in `MEMORY.md` index. Captures the four-way date relationship as a single source of truth so future sessions don't reintroduce date-keying bugs:
    - Report date = Daily Packs day = Excel production date.
    - Report date = attendance PDF upload date + 1 day.
    - フルキャスト 手動入力 shift date = Excel production date − 1 day.
    - フルキャスト 手動入力 shift date = attendance PDF upload date.
  → `~/.claude/projects/-var-www/memory/project_date_rules.md`
- **[verify]** Round-trip on `2026-04-19` Excel:
  - Save response: `{production_date: "2026-04-19", shift_date: "2026-04-18", number_of_packs: 13168, fullcast_saved: 2, plan_lines_saved: {A: 9, B: 8, C: 0}, section_start_time: "19:20"}`
  - SQL: `temp_staff(record_date=2026-04-18)` has the 5名 / 3名 buckets at start_time=19:20; `temp_staff(record_date=2026-04-19)` is empty (correct — that's the production day, not the shift day).
  - Cleaned up stale rows from earlier tests where the old code wrote to production_date. → live test.

## 2026-05-01 — Daily-packs Excel preview cleanup: dropped Input by / Weather / Total qty fields, smarter start time, +30 min end buffer, jump to フルキャスト tab after save
- **[ui]** Removed three unnecessary fields from the Daily Packs Excel preview: **Input by**, **Weather / Temp**, and the **Total quantity** sum (replaced with a compact **Products** count showing `N items` since totals vary per product). The preview is now narrower and shows only the operational fields: Production date · Start time · End time · Products. → `static/console.html`
- **[ui]** **Cross-check pill** in the section-totals strip rewritten. The previous version flagged `⚠ per-product sum 0 ≠ 13,168` as an alarm any time per-product `grand_total` was missing — false alarm because that's expected on these workbooks. New logic compares per-product **N+Y** sum (which IS reliable) with section_totals.combined, allows a 0.5% drift tolerance, and stays silent when the per-product side is genuinely empty. → `static/console.html`
- **[backend]** `_parse_production_plan_sheet` start-time rule changed. Was: first A-line item start. Now: **latest first-item start across all non-empty lines** (A / B / C). The workbook flips which line carries the canonical "main" production vs early prep between months — A-line first = 17:20 in one file but A-line first = 19:20 in another; B-line is the inverse. Picking the latest first-item-start consistently lands on the actual night-shift start (19:20 in both cases). The chosen line is recorded on the parsed plan as `section_start_source_line`. → `main.py`
- **[ui]** Auto-update Start-time `<select>` now **dynamically appends** the parser-suggested value when it isn't already in the dropdown options (so 17:20 / 19:20 from the production plan can be displayed even though the static options were only 17:00 / 19:00). The Start time label gained the hint `(製造予定表)` to make the source explicit. → `static/console.html`
- **[ui]** **End time field** gained an explicit **+30 min buffer** per operator request — `recomputePrediction()` now adds 30 minutes to the computed end-time, and the field label reads `End time (+30 min buffer)`. The hint line shows `Xh Ym run · avg N p/h · +30m buffer` so the buffer is visible. The avg-p/h calc uses the unbuffered run length (no double-counting). → `static/console.html`
- **[ui]** **Post-save navigation** changed: after a successful Excel save, the console now jumps to the **フルキャスト tab** (TAB 2 — `switchTab("fullcast")`) instead of the Daily Packs Manual entry segment, sets `$fcDate` to the Excel's `production_date`, and calls `loadFcFromDb(date)` so the saved 会社 / 人数 rows appear immediately in the existing fullcast list UI. The operator can verify the auto-populated buckets and edit if needed without re-typing them. → `static/console.html`
- **[verify]** Round-trip on `auto_uploads/daily_packs/夜勤用日報２６．０４．１９.xlsm`:
  - Parser returned `section_start_time = 19:20` (chosen from A-line first item; B-line first was 17:20 — the older "earliest" rule would have picked the wrong one).
  - `section_totals = {n_total: 9973, y_total: 3195, combined: 13168}` — pill renders without false alarm.
  - `fullcast = [{5 名, 19h, 製造2課}, {3 名, 19h, 製造2課}]` — matches the operator's verified `5 名 + 3 名 = 8 名` total.
  - SQL after save: `daily_packs(2026-04-19) → number_of_packs=13168, n_total=9973, y_total=3195, section_start_time=19:20`; `temp_staff(2026-04-19)` has 2 rows (5名 / 3名 both starting 19:20, leave 10:00 next-day, total 19h each).
  - `GET /api/temp-staff/2026-04-19` returns `total_people: 8, total_hours: 38.0` — exactly what the post-save fullcast tab will show. → live test.

## 2026-05-01 — Daily-packs Excel parser reads section totals + フルキャスト + A/B/C production plan; saves to DB
- **[backend/parser]** Three new label-search sub-parsers added in `main.py` next to the existing `_parse_pack_sheet`:
  - **`_parse_section_totals_from_input_sheet(ws)`** — scans the top header rows of `入力画面` for `Ｎ合計` / `Ｙ合計` cells (NFKC-folded so half/full-width Ｎ/Ｙ both match), then walks down each label's column for the first numeric cell. Returns `{n_total, y_total, combined, n_label_at, y_label_at}`. Layout-tolerant — the cells sit on the right side of the page after the per-product N便/Y便 grid; their column shifts month over month, so the search is by **text**, not coordinates.
  - **`_parse_fullcast_rows_from_jisei_sheet(ws)`** — finds the `人時生産性` calc-label rows on the `人時生産性` sheet (`人時生産性\\nLabor productivity` in col A), walks back up to two rows that look like a fullcast bucket (small int 1–50 in col A, blank col B, timedelta in col C). Tags each bucket with `製造1課` or `製造2課` based on the closest section-title row above (`人時生産性計算　製造X課`). Returns a list of `{section_label, headcount, total_seconds, total_hours, source_row}`.
  - **`_parse_production_plan_sheet(ws)`** — parses `製造予定表　ＮＹ`. Locates each `Aライン` / `Bライン` / `Cライン` block by label in col A; reads the column-title row directly under each block to find which columns hold `確定` / `Y便` / `N+Y` / `製造時間` / `タイムテーブル` / `切替時間` / `p/h` / `必要人員` / `製造予定数`. **Carries the column map across line blocks** because B and C lines don't repeat every header from A's title row. Walks down until the per-line `Aライン計` / `Bライン計` / `Cライン計` row, captures total. The first A-line item's start time becomes `section_start_time`. → `main.py`
- **[backend]** `parse_daily_pack_excel` now opens the workbook in random-access mode (`read_only=False, keep_vba=False`) so the auxiliary parsers can label-search any sheet, and folds the three new blocks (`section_totals`, `fullcast`, `production_plan`) into the response. `/api/daily-packs/auto-extract-excel` passes them through. When the production plan provides a confirmed start time, it overrides the heuristic-based suggestion. → `main.py`
- **[backend/db]** Migration on app start (idempotent `ALTER TABLE … ADD COLUMN IF NOT EXISTS`):
  - `daily_packs` gained **`n_total`**, **`y_total`**, **`section_start_time VARCHAR(5)`**.
  - New table **`production_plan`** (`record_date`, `line_code CHAR(1)`, `item_name`, `planned_qty`, `n_qty`, `y_qty`, `combined_qty`, `start_time`, `takt_time`, `pph_target`, `required_staff`, `source_filename`, `saved_at`) with `UNIQUE (record_date, line_code, item_name)` and `idx_production_plan_date`. → `main.py`
- **[backend]** `POST /api/daily-packs/save-excel-batch` now persists everything in one transaction:
  1. Per-product rows into `daily_pack_items` (existing flow).
  2. **Day-level row** in `daily_packs` — `n_total` / `y_total` / `section_start_time` go on the same UPSERT (`COALESCE(EXCLUDED, …)` so partial saves don't clobber prior values). When `section_totals.combined > 0` it overrides `number_of_packs` (this is the operator-confirmed Ｎ合計+Ｙ合計, authoritative over the per-product sum which can be 0 if the workbook leaves 全合計 blank — verified on the real 2026-04-29 file: per-product sum = 0, combined = 10,293, fix saves the right number).
  3. **`temp_staff` フルキャスト rows** — replaces this date's rows from the parsed `fullcast[]` (one bucket per row, with `headcount` / `hours_per_person` / `total_hours` derived from `total_seconds`). Operator can opt out via `payload.skip_fullcast: true` — in that case existing rows are left alone.
  4. **`production_plan` rows** — replace this date's rows with the parsed A/B/C breakdown (one row per item, `ON CONFLICT (record_date, line_code, item_name) DO UPDATE`).
  Response now includes `n_total`, `y_total`, `section_start_time`, `fullcast_saved`, `plan_lines_saved: {A,B,C}`. → `main.py`
- **[backend]** New `GET /api/production-plan/<date>` returns the saved A/B/C plan rows for a date plus the section-level `n_total`, `y_total`, `section_start_time` from `daily_packs`. Used by future report views. → `main.py`
- **[ui]** Daily Packs Excel tab in the console gained three new preview cards (in this stacking order, between the start-time/total fields and the per-product table):
  - **Section totals strip** — Ｎ合計 / Ｙ合計 / 合計 with a cross-check pill (✓ matches per-product sum  vs  ⚠ discrepancy with explicit number).
  - **フルキャスト auto-fill block** — shows `8 名 + 1 名 = 9 名 · 27.0h total` (or however many buckets the parser found), with a per-bucket detail line. **Skip checkbox** lets the operator opt out — when checked, the save handler leaves `temp_staff` untouched so manually entered rows aren't overwritten.
  - **A/B/C line preview cards** — three stacked cards (auto-grid, min 220px wide), colour-coded headers (S1 blue, S2 green, S3 orange), each card has a compact 5-column mini-table (item · planned · N · Y · start). Item names are short-truncated to ~12 characters so the card stays readable. Empty lines render an "empty" placeholder. A green `start 17:20` pill at the top shows the confirmed Section-2 start time. → `static/console.html`
- **[ui]** `_saveOneParsed()` was extended to pass `section_totals`, `section_start_time`, `fullcast`, `skip_fullcast`, and `production_plan` through to the save endpoint. The Auto-update click handler now calls `renderXlsxExtras(j)` after `recomputePrediction()` so the new cards populate every time. → `static/console.html`
- **[verify]** Live end-to-end against `auto_uploads/daily_packs/夜勤用日報２６．０４．２９.xlsm`:
  - Parser returns `section_totals = {n_total: 7625, y_total: 2668, combined: 10293}`, `fullcast = [{8 名, 19.0h}, {1 名, 19.0h}]`, `production_plan = {section_start_time: "17:20", totals: {A:5487, B:5131, C:0}}`, **A** has 10 items with start times 17:20 → 23:12, **B** has 5 items including 燕三条/中華そば/とみ田豚まぜ/冷し中華/焼ちゃんぽん, **C** is empty.
  - `POST /api/daily-packs/save-excel-batch` returned `rows_saved: 14, number_of_packs: 10293, plan_lines_saved: {A: 10, B: 5, C: 0}, fullcast_saved: 2`.
  - SQL read-back: `daily_packs(2026-04-29)` row shows `number_of_packs=10293, n_total=7625, y_total=2668, section_start_time=17:20`. `production_plan(2026-04-29)` has 15 rows.
  - `GET /api/production-plan/2026-04-29` returns the A/B/C lines with item-level start times preserved. → live test.

## 2026-04-30 — v3.4 release tag

Bump `app.version` 3.3 → 3.4 to mark a coherent batch shipped on top of v3.3:

- **Day-off Schedule** is now a full feature, not just a planning grid. It can import the existing yearly 定休表 Excel, auto-suggest matches against the roster, persist a one-time nickname-mapping table for future imports, show daily presence/off counts and 6-row efficiency summary (人時 P/h · 前日比 vs prev-day Δ% · 対目標 vs target %), and split the grid into 製造1課 / 製造2課 sub-tabs (default 製造2課) over a 21-to-20 fiscal cycle.
- A global **🚨 Highlight unauthorized absence** toggle on the Day-off tab drives gantt rendering everywhere (desktop, mobile, popup). Absent rows whose date is in the saved off-day list render as calm `休 scheduled`; absent rows that are NOT in the list render red `🚨 Unauthorized` when the toggle is on.
- New **two-flow Auto-update** for the desktop client. The Daily Packs Excel auto-update button (`btnXlsxAuRun`) now has a matching `/api/v1/xlsx/upload` server endpoint, and the bundled `upload_latest.bat` was rewritten with separate `:upload_pdf` / `:upload_xlsx` subroutines plus a CLI mode arg. The Electron IPC recipe in the API guide now distinguishes three Auto-update routes by `kind`.

Detailed per-feature entries follow below.

→ `main.py`, `README.md`, `PROJECT_INSIDE_AI_BLUEPRINT.md`

## 2026-04-30 — Two-flow Auto-update: split PDF and Excel into independent upload + auto-extract pipelines
- **[backend]** New endpoint `POST /api/v1/xlsx/upload` (auth-protected, mirrors `/api/v1/pdf/upload`) — accepts `.xlsx`/`.xlsm` (≤50 MB, validates the `PK\x03\x04` zip magic), writes into the daily-packs watched folder via the new `_resolve_packs_target_dir()` helper. Returns `{ok, filename, size, stored_in, received_from_key}` so the desktop client can confirm the file landed where `auto-extract-excel` will find it. → `main.py`
- **[ops]** Rewrote `upload_latest.bat` with two clearly-labelled subroutines: **`:upload_pdf`** (walks `.\watch\pdf\`, posts to `/api/v1/pdf/upload`, then triggers `/api/v1/pdf/auto-upload?save=true`) and **`:upload_xlsx`** (walks `.\watch\xlsx\`, posts to `/api/v1/xlsx/upload`, then triggers `/api/daily-packs/auto-extract-excel`). New CLI mode arg: `upload_latest.bat pdf | xlsx | all`, default `all`. Watch folders separated so file types never collide. The dispatch block was wrapped in parens — the previous `if cond cmd & goto :done` form had the `&` running `goto :done` UNCONDITIONALLY because CMD doesn't gate post-`&` statements with the `if`, which silently broke any non-PDF mode. Footer now has separate schtasks examples for each flow. → `upload_latest.bat`, `upload_latest.bat.bak`
- **[docs]** API guide §3 gained a "Two-flow Auto-update (PDF + Excel) — recommended" section with side-by-side `[A]` and `[B]` curl recipes. The Electron `main.js` IPC handler example in §4.3 was rewritten: a `ROUTES` dict with three explicit kinds (`attendance` / `daily_packs_pdf` / `daily_packs_xlsx`) replacing the old binary `kind === 'daily_packs' ? … : …` form. Two new IPC upload handlers (`upload-pdf`, `upload-xlsx`) and matching `preload.js` exposures (`window.desktop.uploadPdf`, `window.desktop.uploadXlsx`) so renderer code never has to hand-build `FormData`. Bilingual warning that the two flows return different response shapes — attendance returns `{saved, records_processed, batch_id, mismatches, …}`, the Excel flow returns `{source_filename, meta, products, start, prediction}`. → `API_APP_GUIDE.md`
- **[verify]** End-to-end smoke test against `/home/pi/DATA/UPLOAD/2026年度（2.21～6.20）定休表.xlsx` (306 KB) via the new endpoint → file lands in `/var/www/attendance_app/auto_uploads/daily_packs/`. Direct call to `/api/daily-packs/auto-extract-excel` returns the correct shape (`source_filename`, `meta.production_date`, `products[]`, `start`, `prediction`) on the existing test file. → live test.

## 2026-04-30 — Day-off: section sub-tabs, 21-to-20 cycle, efficiency rows, unauthorized-absence toggle that drives gantt highlights
- **[backend]** `dayoff_schedule.json` now also stores a global `highlight_unauthorized` boolean flag. New endpoint `POST /api/dayoff/highlight-unauthorized` body `{enabled: bool}` flips it without touching the schedule (atomic write under `_DAYOFF_LOCK`). The existing `PUT /api/dayoff/schedule` preserves the flag if not explicitly set in the payload, so saving the schedule never accidentally clears it. `GET /api/dayoff/schedule` now also returns the flag. → `main.py`
- **[ui]** Day-off Schedule tab is now **section-scoped** with two sub-tabs above the toolbar — **`📋 製造1課`** and **`📋 製造2課`**, default = **製造2課** (matches the heavier roster). Switching sub-tabs filters the grid (rows + summary counts) to the chosen section only. Sub-tab pill colours match the gantt section colours (S1 blue, S2 green). The toolbar gained a fiscal-cycle preset **`📆 This cycle (21–20)`** that snaps the date range to the office's 21st-to-20th cycle (e.g., today 2026-04-30 → 2026-04-21 → 2026-05-20, labelled `2026-05 cycle (4/21–5/20)`); the previous **Calendar month** button is kept as an alternative. → `static/management.html`
- **[ui]** Three new efficiency-summary rows are stacked on top of the day-off grid (under the existing 出勤 / 休 / 休% rows): **`人時 · P/h`** (per-day section P/h), **`前日比 · vs prev`** (▲/▼ + Δ% vs the previous data day), **`対目標 · vs target`** (▲/▼ + % deviation from S1=85, S2=35). Both arrow rows are colour-coded (green up, red down, gray flat) so a glance shows if a planned-off day correlates with a productivity dip. P/h numbers come from the existing `/api/m/summary` rolling endpoint; the active section's target is read from a new client-side `DO_TARGETS` map matching the summary page. → `static/management.html`
- **[ui]** Toggle button **`🚨 Highlight unauthorized absence on report`** added next to the Save button on the Day-off tab. When checked, all gantt renders (everywhere — desktop, mobile, popup) highlight absent rows whose absence is **NOT** in the saved day-off list as red `🚨 Unauthorized` (with a red row background + left border). The toggle uses the new `POST /api/dayoff/highlight-unauthorized` endpoint and is server-side persisted, so all users see the same setting. → `static/management.html`
- **[ui]** Gantt page (`/gantt` and via popup `?report=1`) now fetches `/api/dayoff/schedule` alongside the gantt data on every load. `_GanttDayoff` cache holds `{schedule, highlight, currentDate}`. The `cls === 'absent'` branch in `renderRow()` was extended:
  - **scheduled off** (absent + date ∈ employee's day-off list): renders a calm `休 scheduled` pill in green, even when the highlight toggle is OFF (so operators can always see who is *legitimately* off);
  - **unauthorized** (absent + toggle ON + date NOT ∈ list): renders a red `🚨 Unauthorized` pill with a tinted row background and a red left-border;
  - **default** (highlight toggle off, no day-off entry): renders the existing faint "Absent" label, behaviour unchanged.
  → `static/gantt.html`
- **[verify]** End-to-end: toggle round-trip via `POST /api/dayoff/highlight-unauthorized` → `GET /api/dayoff/schedule` → flag persists. Test schedule contains 2026-02-25 and onwards for `00000320` (青山 京子, 製造2課). Gantt renders show the calm `休 scheduled` pill on those dates regardless of toggle; flipping the toggle ON makes other absent rows turn red. → live test.

## 2026-04-30 — Day-off: 定休表 Excel importer + name-mapping wizard + daily summary strip
- **[backend]** Two new endpoints power the import workflow.
  - `POST /api/dayoff/import-excel` (multipart `file`) parses the yearly 定休表 .xlsx with `openpyxl` (read-only, magic-byte check, 25 MB cap), iterates every monthly sheet skipping `初期設定`, walks each data row from row 5 onward, collects every string in column 11+ that isn't a known column-header label (built-in 30-entry blocklist for `工場長`, `昼社員`, `2課役職`, `製造1課`, `製麺社員`, `行事・備考`, `祝日`, etc.), and resolves each Excel name in priority order: (1) saved nickname map → code, (2) exact normalized match against `EMPLOYEE_ROSTER`. Returns matched entries + a per-distinct-name unmatched list with **auto-suggestions** (roster employees whose normalized full-name contains, starts-with, or ends-with the unmatched nickname — capped at 8 suggestions). Also returns date range and per-sheet stats.
  - `POST /api/dayoff/apply-import` accepts `{entries:[{code,date}], mappings:{nickname:code}, mode:"merge"|"replace_range"}`. Validates each date matches `YYYY-MM-DD` and each code is in the roster (drops invalid silently). Persists `mappings` to `nickname_map.json` (chmod-friendly, atomic-write under `_NICKNAME_LOCK`) so future imports auto-match. Folds entries into `dayoff_schedule.json`: in `merge` mode union onto existing; in `replace_range` mode wipe existing entries within the imported `[date_min..date_max]` window for affected codes first, then add. Returns counts.
  - New helpers: `_norm_name` (strips ideographic + half/full-width spaces from Japanese names so `"青山 京子"` matches `"青山京子"`), `_build_roster_index`, `_nickname_load`/`_nickname_save`, `_DAYOFF_HEADER_BLOCKLIST`. → `main.py`
- **[ui]** Day-off Schedule tab gained a **`📤 Import 定休表 (.xlsx)`** button in the toolbar. Clicking opens an inline import panel with file picker + status line. After upload it shows a stats strip (`<range>`, `N matched`, `M unmatched (D distinct nicknames)`) plus a mapping table — one row per unmatched nickname with the count, the first-seen date, and a `<select>` dropdown grouped into **Suggested** (highlighted optgroup with the auto-suggestions, the single-suggestion case is preselected with an "auto" pill) and **All employees** (full roster). Mode radios: **Merge** vs **Replace existing entries in window**. Apply triggers a save-mappings + re-parse + apply round-trip so newly-mapped nicknames are automatically expanded into per-date entries before the schedule is updated. → `static/management.html`
- **[ui]** Day-off grid gained a **daily summary header strip** above the data rows: 出勤 (Present), 休 (Off), 休率 (Off %) — three rows with a count per visible date. Off-rate cells get colour-graded: ≥30 % red (`hot` class), ≥15 % amber (`warn`), else neutral. A separate strip above the grid shows roster size, days in view, total off-cells, average off / day, and average off-rate across the full window. Numbers update live as the operator toggles cells (no save needed). → `static/management.html`
- **[ops]** `nickname_map.json` added to `.gitignore` alongside `dayoff_schedule.json`. Both files are per-deployment state. → `.gitignore`
- **[verify]** End-to-end smoke test against the user's actual file `2026年度（2.21～6.20）定休表.xlsx`: 8 monthly sheets parsed, date range **2026-02-21 → 2026-06-20**, **2,238 off-cells** scanned, 17 exact matches (`リホン → 00004019 リ ホン` × 17 dates), **77 distinct unmatched nicknames**, 9 with single-candidate auto-suggestions (e.g., `志垣 → 00000401 志垣 靖人`, `杉本 → 00000326 杉本 ｿ-ﾊﾟ-`). The remaining ~68 names are office / admin / contract staff that aren't in the production roster — the import UI lets the operator skip them. → live test.
- **[next]** Phase 2 (deferred to next round): use the saved `dayoff_schedule.json` from gantt rendering — if an employee is absent on a date that **isn't** in their off-day list, render them with a red "unauthorized absence" highlight; if it is in the off-day list, render as a neutral 休 cell.

## 2026-04-30 — v3.3 release tag

Bump `app.version` 3.2 → 3.3 to mark a coherent batch of UI / data-management changes shipped today on top of v3.2:

- Unified site header on every page (single source of truth via `static/site_header.js`); Grafana link removed; `🌐 Dashboard` placeholder tab added.
- Reports page is a read-only popup launcher; `?report=1` flag suppresses the top nav so the gantt / summary popup window is a focused view.
- Management page reorganised into three tabs: **📋 Roster · 名簿管理**, **📅 Day-off Schedule · 休暇予定表** (new feature, persisted to `dayoff_schedule.json`), **💬 LINE Recipients · LINE 通知先** (moved here from the Reports page).
- LINE recipient management endpoints (`/api/line/recipients/{rename,delete}`) plus the day-off persistence endpoints (`GET / PUT /api/dayoff/schedule`).
- Mobile viewer chart improvements: tap-to-rotate fullscreen, touch-driven tooltip with rotation-aware hit-testing (`getScreenCTM().inverse()`), Month default + all four legend chips ON.

Detailed per-feature entries follow below.

→ `main.py`, `README.md`, `PROJECT_INSIDE_AI_BLUEPRINT.md`

## 2026-04-30 — Management page reorganized: 3 tabs (Roster / Day-off / LINE Recipients)
- **[backend]** New persistence file `dayoff_schedule.json` (gitignored) holding `{ schedule: {employee_code: ["YYYY-MM-DD", …]}, updated_at }`. New endpoints: `GET /api/dayoff/schedule` returns the saved schedule; `PUT /api/dayoff/schedule` validates each date matches `^\d{4}-\d{2}-\d{2}$`, validates each employee code is present in `EMPLOYEE_ROSTER` (silently drops unknown codes so the UI stays lenient), de-duplicates and sorts the dates per code, atomic-replaces the JSON file under `_DAYOFF_LOCK`. → `main.py`
- **[ui]** Management page (`/management`) reorganized into a 3-tab layout — the existing roster UI is unchanged but now lives inside its own tab, and two new tabs were added next to it. Tab labels are bilingual: **`📋 Roster · 名簿管理`**, **`📅 Day-off Schedule · 休暇予定表`**, **`💬 LINE Recipients · LINE 通知先`**. Tab switching is purely client-side (no route change); each tab's content lazy-initializes the first time it's opened. → `static/management.html`
- **[ui]** **Day-off Schedule tab** — a sticky-header grid with employees as rows (grouped by section, in `sections.json` order) and dates as columns. Each cell is one tap: toggle off-day on / off (cyan-orange "OFF" pill when set). Header row shows date + Japanese day-of-week (`日月火水木金土`); weekend columns get a soft red tint. The toolbar has From/To date pickers, **This month** + **Next 30 days** range presets, a Saved/Unsaved status pill, and Save/Reset buttons that only enable when the draft differs from the saved baseline. Hard cap at 184 days (≈6 months) to keep the grid responsive. Legend at bottom with last-saved timestamp. → `static/management.html`
- **[ui]** **LINE Recipients tab** — moved verbatim from the Reports page's "LINE bot" card. Each registered userId/groupId now renders as a row with: kind / display_name / id / registered_at + **✎ Rename** + **✕ Remove** buttons calling the existing `/api/line/recipients/rename` and `/api/line/recipients/delete` endpoints. Plus a global **💬 Send Hi (test)** button next to **↻ Refresh**. Bilingual help text + status line for ok/err feedback. → `static/management.html`
- **[ui]** Reports page (`/reports`) — the LINE bot card and its associated `btnLineHi` / `btnLineList` / `refreshRecipients` JS handlers were removed. Replaced with a one-line pointer: *"LINE recipient management … moved to Management → 💬 LINE Recipients"* linking back to the new home. → `static/reports.html`
- **[ops]** `dayoff_schedule.json` added to `.gitignore` under "Mutable per-instance state" so per-deployment off-day data never leaks into the repo. → `.gitignore`
- **[ops]** Round-3 backups (`*.bak3`) of `main.py`, `management.html`, `reports.html` created before edits — independent of the earlier `.bak` and `.bak2` snapshots. → `*.bak3`
- **[verify]** Restart clean. Endpoints live: `GET /api/dayoff/schedule` returns `{schedule: {}, updated_at: null}` on first run; round-trip `PUT {schedule:{"00000320":["2026-05-01","2026-05-02"]}}` → `GET` returns the saved entries with a fresh `updated_at` timestamp. `/api/management/bootstrap` returns the existing roster shape (`sections:[{id,label,codes}]`, `employees:[{code,name,section_id,section_label}]`) which the day-off grid groups by `section_id`. → live test.

## 2026-04-30 — Unified site header on every page (single source of truth, no Grafana, no popup Reports)
- **[ui/new]** Created `static/site_header.js` — a single self-contained header injector. Builds `<header class="site-topbar">` with brand, nav (🌐 Dashboard / Console / Gantt / Summary / Reports / Management), `#healthPill` (60s `/api/health` poll), and `#clockBox` (live time + computed Shift / Prod dates using the same 10:00→08:30 production-cycle rule as the rest of the app). Injects its own scoped `<style>` with literal colors so it works on any page regardless of host CSS variables. Active link is auto-detected from `location.pathname` (also recognises `/m/report` → Gantt and `/m/summary` → Summary). Hidden under `body.mobile` so the mobile viewer pages stay clean. → `static/site_header.js`
- **[ui]** Replaced every page's own nav with the shared header. Each of `console.html`, `gantt.html`, `summary.html`, `reports.html`, `management.html`, `dashboard.html` now: imports the script (`<script src="./static/site_header.js" defer>`), keeps a single `<div id="siteHeader"></div>` placeholder, and has its old `<header class="topbar">` / inline-styled nav block removed. The previous duplicated `clock + health pill` JS in `console.html` (≈30 lines) was deleted — the shared script owns those IDs now. → all six page files
- **[ui]** **Reports nav link** is now a plain `<a href="./reports">Reports</a>`. The `target="_blank"` + `window.open(...,'rndReportsWin',...)` popup behavior was dropped everywhere it appeared (console, gantt, summary, management). The Reports launcher's per-card `📂 Open Report ↗` buttons still call `window.open()` with size hints — those are intentional, the nav link is not. → all six page files
- **[ui]** **Grafana link removed** from every page's nav (was previously labelled `Dashboard ↗` then renamed to `Grafana ↗`). Grafana stays accessible directly via `/grafana/` but no longer clutters the in-app nav. The only remaining Grafana reference in user-facing files is in `admin.html`, which has its own admin nav and is out of scope.
- **[ui]** Page-local headers were trimmed to fit under the unified one: `summary.html`'s old card-topbar (brand + nav + Print/Send) loses the brand+nav portion and keeps just the Print/Send button strip; `management.html`'s topbar (brand + nav + Save/Reset/Lock toolbar) loses brand+nav and keeps just the Save/Reset/Lock toolbar (now `.mgmt-toolbar`).
- **[ops]** Round-2 backups (`*.bak2`) created for every touched file before edits, so this round is independently revertable from the prior `.bak` round. → `*.bak2`
- **[verify]** Restart clean. All routes return 200 (`/dashboard`, `/console`, `/gantt`, `/summary`, `/reports`, `/management`, `/static/site_header.js`). Served pages each contain `<script src="./static/site_header.js" defer></script>` + `<div id="siteHeader"></div>`. No stray "Grafana ↗" / "Dashboard ↗" labels remain in the user-facing nav. No `rndReportsWin` window.open invocations remain on nav links. → live test.

## 2026-04-30 — Toolbar refactor (path B): green Dashboard tab, Reports as popup launcher
- **[backend]** New route `GET /dashboard` → serves a placeholder `static/dashboard.html` with a "🚧 開発中 · Under development" hero block. Reserved as the landing for the new green Dashboard nav tab; real KPI/AI content TBD in a separate work batch. → `main.py`, `static/dashboard.html`
- **[ui]** Added a green-filled `🌐 Dashboard` link as the **first** item in every page's nav: console, gantt, summary, reports, management. Each page got a `.topnav a.dash-link { background:#10b981; color:#fff; }` style block (with the inline-styled equivalent in `gantt.html`). The legacy `Dashboard ↗` link that pointed to `/grafana/` is renamed to `Grafana ↗` everywhere it appeared. → all five page files
- **[ui]** Reports page (`/reports`) is now a **read-only launcher**. The two cards each have **one** button: `📂 Open Report ↗`. Clicking opens the gantt or summary in a **separate popup window** (`window.open(..., 'rndReportView', 'width=1280,height=900,resizable=yes,scrollbars=yes,toolbar=no,menubar=no')`). Subsequent clicks reuse the same popup window via the named target. The per-card `💬 Send to LINE` buttons + their handlers + the `sendToLine` orphan listeners were removed — that flow now lives **inside** the popup windows themselves. The lede was updated bilingually to explain the new flow. → `static/reports.html`
- **[ui]** Reports nav links across the app open the page as a popup window: `<a href="./reports" target="_blank" rel="noopener" onclick="window.open('./reports','rndReportsWin','width=1280,height=900,…');return false;">Reports ↗</a>`. Same on the inline-styled gantt toolbar. Falls back to a normal new tab if the browser blocks the popup. → `console.html`, `gantt.html`, `summary.html`, `management.html`
- **[ui]** Summary page (`/summary`) gained a **`💬 Send to LINE`** button next to the existing `🖨 Print` (renamed from `⬇ PDF`) so the popup-window viewer can send via LINE without leaving the window. New handler lazy-loads `html2canvas`, snapshots the KPI grid, uploads to `/api/line/send-mobile-link`, and shows a status string next to the button. → `static/summary.html`
- **[verify]** All six routes return 200 on restart (`/dashboard`, `/reports`, `/console`, `/gantt`, `/summary`, `/management`); no startup errors in `journalctl`. Spec discrepancies (no `templates/` dir, no wizard bar, no Lock/Unlock pills, no Schedule button — all assumed by the spec but absent from this codebase) were flagged before editing and explicitly deferred to phase 2 rather than implementing them as new features. → live test.

## 2026-04-30 — v3.2 follow-up: smart Buttons Template card, mobile viewer, recipient management
- **[backend]** New `POST /api/line/send-mobile-link` — multipart `file` (PNG/JPEG, ≤5 MB, magic-byte checked) + `report_date` + `type`. Saves to `static/line_images/<type>_<date>.<ext>` and pushes a single **LINE Buttons Template card** per recipient (thumbnail + title + body + button + `defaultAction` link). Replaces the older two-message (image + text) flow with one composed card. Server helper `_line_push_button_template()` handles title/text/altText length caps. → `main.py`
- **[backend]** New `GET /m/report` and `GET /m/summary` routes — serve the existing `static/gantt.html` and `static/summary.html` so the graphics are 100% identical to `/gantt` and `/summary`. The HTML files themselves detect the `/m/…` URL path and add `body.mobile`, hiding admin chrome (top nav links, Print/PDF/Reload buttons, Member Hours tab, compare-previous and target-line toggles). → `main.py`
- **[backend]** New `GET /api/m/summary?date=Y-M-D&days=N` (1..92) — rolling-N-day aggregate. Iterates the existing `gantt_for_date()` per day and returns `{anchor, start, days, days_with_data, total_packs, s1/s2/combined_total_hours, s1/s2/combined_avg_lp, rows[]}`. Used by the Reports-page snapshot builder when rendering the summary KPI image. → `main.py`
- **[backend]** New `POST /api/line/recipients/rename` (body `{id, display_name}`) and `POST /api/line/recipients/delete` (body `{id}`) — both guarded by `_LINE_LOCK` so concurrent webhook auto-registration cannot lose updates. Display name capped at 60 chars. → `main.py`
- **[ui]** Reports page (`/reports`) — both **💬 Send to LINE** buttons now: build the 4-box snapshot HTML (2×2 grid for chat-preview readability, 520 px wide), render to PNG with `html2canvas`, upload via `send-mobile-link`, surface live status next to the message strip. The **List recipients** card now renders one row per recipient with `kind`, the new editable `display_name`, and **✎** rename + **✕** delete inline buttons calling the new endpoints. → `static/reports.html`
- **[ui]** Gantt page (`/gantt`) — added `MOBILE_MODE` detector at top of the `<script>` block. When the page is served at `/m/report` (or `?mobile=1`), the script injects a `<base href>` element pointing back to `/attendance/` so all relative `fetch('api/…')` calls resolve correctly (otherwise they would 404 against `/attendance/m/api/…`). Mobile-mode CSS hides the toolbar nav, Refresh, Download PDF, Send PDF to LINE buttons, and the Member Hours tab + panel. → `static/gantt.html`
- **[ui]** Summary page (`/summary`) — added the analogous mobile-mode block at the top of the script and a CSS `body.mobile { … }` group hiding `.topbar-links`, `#btnPrint`, `#btnReload`, the Compare/Targets toggles. The `BASE` constant was patched to handle `/m/summary` correctly (was incorrectly producing `/attendance/m`). Default `state.range` flipped from `week` → **`month`**, and all four legend chips (S1, S2, Combined, **Packs**) now default ON. Legend rendering grew a long/short label pair with `translate="no"` so browsers' auto-translate cannot expand `S1` into `Manufacturing Department 1: Labor Productivity per Hour (S1)`. → `static/summary.html`
- **[ui]** Summary page — chart fills more of the screen on phone: `body.mobile .chart-svg{ height:54vh }` portrait, `78vh` landscape; axis labels bumped to 13 px. **Tap-to-rotate fullscreen** added: tap the chart → `body.fs-chart` overlay covers viewport, the SVG gets `transform: rotate(90deg)`, and floating ↻ re-rotate + ✕ close buttons appear top-right; Android Chrome also requests Fullscreen API + `screen.orientation.lock('landscape')`. Touch handlers (`touchstart` / `touchmove` on `chartBox`) drive the existing tooltip — hit-testing uses `svg.getScreenCTM().inverse()` so it stays accurate under any CSS transform. → `static/summary.html`
- **[ops]** New static directory `static/line_images/` is gitignored (joined with the existing `static/line_pdfs/`). Both are auto-created at startup. → `main.py`, `.gitignore`
- **[docs]** `API_APP_GUIDE.md` extended with section **"8. LINE Messaging API integration (v3.2)"** — covers configuration (`line_config.json` schema), credential sourcing (Developers Console + manager.line.biz toggles), all eight `/api/line/...` endpoints with request/response shapes, the three mobile viewer routes, the bootstrapping flow for a new recipient, and a copy-paste curl quick-test. → `API_APP_GUIDE.md`
- **[verify]** Live: webhook auto-registers `Ube67de00fe2a3e138cc46e34ae46914f` (renamed to `creator`); **List recipients** shows the row with rename/delete buttons; **💬 Send to LINE** delivers a single Buttons Template card with the 2×2 image, title `勤怠記録 · Attendance Report`, body `📅 2026-04-28　タップで詳細を表示`, button `📊 View Report` → opens `/m/report?date=2026-04-28`. The mobile gantt page renders the same data as `/gantt` (verified IN/OUT visible per row, Member Hours tab gone). The mobile summary page renders the same chart as `/summary`, defaults to Month with all 4 series, tooltip works on tap, fullscreen rotation works with ✕ close. → live test.

## 2026-04-30 — v3.2: LINE Messaging API integration (webhook + push + client-rendered PDF)
- **[backend]** Bumped FastAPI app version `3.0` → `3.2` to mark the LINE feature release. → `main.py`
- **[backend]** New `line_config.json` (chmod 600, gitignored) holds `channel_id`, `channel_secret`, `channel_access_token`, `public_base_url`, and a `recipients[]` array that the webhook self-populates. → `line_config.json`
- **[backend]** `POST /api/line/webhook` — verifies `X-Line-Signature` HMAC-SHA256 against the channel secret, parses LINE events, registers `userId` / `groupId` / `roomId` of any sender into `recipients[]`, and replies via `/v2/bot/message/reply` with either a registration confirmation or — when the user types `report` / `report YYYY-MM-DD` — the gantt page URL for that date. Empty/probe payloads (LINE's "Verify" button sends one) return 200 with `{"ok": true}`. → `main.py`
- **[backend]** `POST /api/line/send` (no auth, browser-facing like the gantt API) — body `{report_date, type}` pushes a text+link to all registered recipients via `/v2/bot/message/push`. Validates `report_date` and refuses with a clear 400 when no recipients are registered yet. → `main.py`
- **[backend]** `POST /api/line/upload-and-send` — multipart endpoint accepting `file`, `report_date`, `type`. Validates `%PDF-` magic bytes and a 12 MB cap, saves the upload to `static/line_pdfs/<type>_<date>.pdf` (overwrite-on-resend per date), and pushes the public URL to all recipients. → `main.py`
- **[backend]** `POST /api/line/test-hi` and `GET /api/line/recipients` — small helpers used by the Reports page LINE card. → `main.py`
- **[backend]** Helpers `_line_load`, `_line_save`, `_line_verify_signature`, `_line_api_call`, `_line_push`, `_line_reply`, `_line_register_recipient`. Use `urllib.request` (no new pip deps) and `hmac.compare_digest` for constant-time signature comparison. Recipient registration is guarded by a module-level `threading.Lock`. → `main.py`
- **[ui]** Reports page (`/reports`) — each report card got a **💬 Send to LINE** button next to **Open in new tab ↗**, plus a new **LINE bot** card at the bottom with **💬 Send Hi (test)** and **List recipients** buttons (pretty-prints the registered userIds/groupIds + timestamps). → `static/reports.html`
- **[ui]** Gantt page (`/gantt`) — toolbar gained **💬 Send PDF to LINE** next to **⬇ Download PDF**. Click → lazy-loads `html2pdf.js` from jsDelivr, renders the `.page` element to an A4 portrait PDF blob (scale 2, margins 6 mm), uploads to `/api/line/upload-and-send`, and shows live status next to the button (`loading PDF library… → rendering PDF… → uploading… → ✅ sent to N recipient(s) — <url>`). → `static/gantt.html`
- **[ops]** New nginx requirement (already in place): `https://rnd.asiakawaii.com/attendance/api/line/webhook` is the URL pasted into the LINE Developers Console (Messaging API tab → Webhook URL → Use webhook ON). Auto-reply / Greeting messages must be **OFF** in `manager.line.biz` for user messages to reach the webhook.
- **[ops]** `.gitignore` extended to exclude all secret/state files: `line_config.json`, `api_keys.json`, `admin_config.json`, `known_clients.json`, `known_ips.json`, `announcement.json`, `auto_upload_config.json`, `auto_uploads/`, `logs/`, `static/line_pdfs/`, `*.bak`. Verified that no secrets were ever committed historically. → `.gitignore`
- **[verify]** Live: webhook **Verify** button in LINE Developers Console returns ✅ Success. Test phone (+81 80-6402-2774) friended the bot, sent a message → recipient registered as `Ube67de00fe2a3e138cc46e34ae46914f` (kind=`user`). Reports-page **Send Hi** delivered "Hi 👋 (test from V3 Attendance Console)" to the phone. End-to-end PDF send from the gantt page is shipped pending the next user test. → live test.

## 2026-04-28 — Member Hours: gantt-style daily strips + per-day p/h, drop "Hours per day" chart
- **[backend]** `/api/members/compare` now hard-caps the requested range at **92 days (3 months)** — anything wider returns HTTP 400. Keeps the new aggregate query bounded and the daily-strip render responsive. → `main.py`
- **[backend]** Each `days[]` cell now includes `pph` (per-day section p/h = `daily_packs.number_of_packs / total_section_hours_for_that_date`). One bounded query batches per-section per-date hours (regular attendance + temp_staff folded into 製造２課) plus the daily packs counts; results are attached to every cell after the existing aligned-axis pass. → `main.py`
- **[backend]** Per-member `summary` block expanded: now also returns `earliest_in`, `latest_in`, `earliest_out`, `latest_out`, and `max_pph` (best p/h across days the member actually clocked in). `avg_in`/`avg_out`/`longest_day` are kept for backward compatibility. → `main.py`
- **[ui]** Removed the **Hours per day** SVG line chart entirely (the `memChart` / `memLegend` mem-card and the whole `renderChart()` function). Member Hours now renders one block per selected member, top-to-bottom, so multiple members can be visually compared at the same time slot. → `static/gantt.html`
- **[ui]** New daily-strip layout mirrors the gantt section/employee rows: a coloured **member header bar** (name · code · section · `total hrs · days · max p/h`), the same `10:00 → 08:30` axis ticks the gantt uses, and one row per date in the requested range with a date+DOW name cell, an IN→OUT bar (dual `IN ··· wh · OUT` label inside, narrow rows fall back to just `wh`), and a right-side stat column showing `wh · p/h X.XX` for that day. Off days render an empty track and a "—" stat. → `static/gantt.html`
- **[ui]** New CSS block `.mem-mblock / .mem-mhead / .mem-axis / .mem-drow / .mem-dcell / .mem-dtrack / .mem-dright` reuses the existing `.track` / `.seg` math (via `toAxis` / `toPct`) so the new strip lines up pixel-for-pixel with the gantt's time window, including overnight shifts (OUT bumped past midnight when `outH <= inH`). → `static/gantt.html`
- **[ui]** Totals card now reports per-member: **Days worked · Total hrs · Earliest IN · Latest IN · Earliest OUT · Latest OUT · Longest day · Max p/h**. The previous `Avg IN`/`Avg OUT` columns were dropped from the table view (still returned by the API for compatibility). → `static/gantt.html`
- **[ui]** `runCompare()` now blocks ranges > 92 days client-side with a clear message before round-tripping, matching the new backend cap. → `static/gantt.html`
- **[verify]** Live: `compare?from=2026-04-01&to=2026-04-28&codes=00004019` returned `pph` on every cell where packs > 0, `summary.max_pph = 105.71`, `earliest_in 10:43 / latest_out 19:08`, `days_worked = 8`. 365-day range correctly returns 400 with `Range cannot exceed 3 months (92 days)`. → live test.

## 2026-04-28 — Gantt Productivity tab → Member Hours (per-member compare with section toggle)
- **[backend]** New `GET /api/members/list?section=all|1|2` returns the section-filtered roster (`code`, `name`, `section_id`, `section_label`); built from `EMPLOYEE_ROSTER` + `SECTION_OF_CODE`. → `main.py`
- **[backend]** New `GET /api/members/compare?from=YYYY-MM-DD&to=YYYY-MM-DD&codes=A,B,C` (codes capped at 30) returns one entry per member with a `days[]` array aligned to the requested date range — each cell `{date, in, out, work_hours}` (None when no record). Each member also gets a `summary` block: `days_worked`, `total_hours`, `avg_in`, `avg_out`, `longest_day`. New helper `_hhmm_to_hours`. → `main.py`
- **[ui]** Removed the entire **📊 Productivity** tab (DOM `prod-wrap` + `Productivity = (() => {...})()` IIFE, ~230 lines). Replaced with **👥 Member Hours**. → `static/gantt.html`
- **[ui]** New tab UI: **section toggle** (Both / 製造１課 / 製造２課), **search box** with autocomplete dropdown (matches name OR code), **multi-select chips** (up to 12 members, color-coded, removable with ×), **From / To date pickers** (defaults to last 7 days), and a **Compare →** button. → `static/gantt.html`
- **[ui]** Result view: (1) **multi-line SVG chart** — X = date, Y = hours worked, one polyline per member, hover dot tooltips show `MM-DD: H.hh · IN→OUT`; (2) **per-member day-strip** — one row per selected member, one cell per day in range, IN→OUT bar painted with the same axis math as the gantt timeline so the visual language matches; (3) **totals table** — days_worked, total_hours, avg_in, avg_out, longest_day per member. → `static/gantt.html`
- **[ui]** Section change drops any selected members not in the new section. Removing a chip auto re-numbers colors and re-renders the result without a server round-trip. Empty state has a clear "Pick at least one member, choose a date range, then click Compare →" hint. → `static/gantt.html`
- **[verify]** Live check: `section=2` returned 47 members, `section=1` returned 29, `all` returned 76. `compare` for `00000115, 00000324, 00000326` over 2026-04-16…04-22 returned proper days_worked / total_hours / avg_in / avg_out per member. → live test.

## 2026-04-28 — Gantt: drop midnight line, restrict pack lines to 製造２課, multi-Excel upload
- **[ui]** Removed the per-row red **midnight 00:00 vertical line** from the Gantt timeline. Axis tick label keeps its existing styling. Less visual noise on every row. → `static/gantt.html`
- **[ui]** **Pack production start/end lines** (dashed green / dashed amber) and the legend now appear **only on the 製造２課 section**, since 製造１課 doesn't run the daily packs line. New `PACK_LINE_SECTIONS = new Set(["製造２課"])` gates both the per-row line painting and the legend strip; `renderRow(emp, sectionLabel)` now takes the section label so it can decide. → `static/gantt.html`
- **[ui]** **Multi-Excel upload** in the Daily Packs tab. The file input gained `multiple`; the change handler now parses every selected file in sequence and renders a per-file queue table (filename / date / products / total qty / start→end / status). The detailed preview shows the first successfully-parsed file; **Confirm & Save all batches (N) →** loops the queue and saves each as its own batch via `/api/daily-packs/save-excel-batch`. Status pills update live (queued → parsing → parsed → saving → saved/failed). After all saves, the page transitions to Manual entry on the LAST saved date. Single-file flow (and Auto-update) keep their original UX — queue stays hidden. → `static/console.html`
- **[verify]** Live three-file parse via curl: `２６.０４.２０` (16 products, 12,277), `２６.０４.２１` (16, 11,649), `２６.０４.２２` (15, 12,486) — all parsed cleanly. → live test.

## 2026-04-28 — Daily Packs note provenance + Confirm-and-Save next-step + Gantt pack-time lines
- **[backend]** `daily_packs.note` now carries provenance for every save. Excel save accepts a new `source_method` field (`excel` / `excel-auto`) and writes the row's note as `"[<source_method>] <filename> N products batch <id8>"`. PDF Confirm & Save and PDF Auto-update prefix `[pdf]` / `[pdf-auto]`; manual entry prefixes `[manual]`. Operators can now see at a glance how each day's count was entered. → `main.py`, `static/console.html`
- **[ui]** Manual-entry Note input gains a placeholder + hint line explaining the auto-fill behavior so users don't wonder where the `[manual]` / `[excel-auto]` tags come from. → `static/console.html`
- **[ui]** After Excel **Confirm & Save batch →** succeeds, the page transitions to the Manual entry segment with the production date pre-loaded, triggering `loadPackFromDb()` so the operator immediately sees the saved row + the auto-stamped note (the "next step" UX the user asked for). → `static/console.html`
- **[ui]** PDF Auto-update tags every extracted result with `__autoSource: true` so the bulk-save endpoint marks them `[pdf-auto]` instead of `[pdf]`. → `static/console.html`
- **[ui]** Gantt timeline now draws **two extra vertical lines per row** beside the existing red midnight line: dashed **green** at the production start time and dashed **amber** at the predicted end time, both pulled from the latest `daily_pack_items` row for the displayed date. A small legend strip above the axis (rendered only when start/end are known) labels each line with its time. Lines align with `MN_PCT` math so they match the gantt's 10:00 → 08:30+24 axis. → `static/gantt.html`
- **[verify]** Smoke test: posted Excel save with `source_method=excel-auto` → `daily_packs.note = "[excel-auto] 日報、各作業指示書２６.０４.２２.xlsx 1 products batch b35940e4"`, items GET returned `start=17:00 end=23:16`. Gantt page will pick those up via `loadPackTimes(date)` and paint the lines. → live test at 09:05.

## 2026-04-28 — Daily Packs Excel: dual-table save, Auto-update button, tab reorder
- **[backend]** `/api/daily-packs/save-excel-batch` now also upserts `daily_packs` with `number_of_packs = sum(grand_total)` and a note like `"xlsx batch <id8> · N products · <filename>"`. One click writes both the per-product detail (`daily_pack_items`) and the day's pack-count summary used by productivity / gantt / summary report. Response gains `number_of_packs`. → `main.py`
- **[backend]** New `POST /api/daily-packs/auto-extract-excel` mirrors the existing PDF auto-extract: picks the latest `.xlsx` (or `.xlsm`) in `DAILY_PACKS_AUTO_UPLOAD_DIR`, ignores Office lock files (`~$…`), parses, and returns the same shape as `/api/daily-packs/extract-excel` so the frontend can reuse the same render path. New helper `_pick_latest_xlsx_in()`. → `main.py`
- **[ui]** Daily Packs segment tabs reordered: **Upload Excel | Upload PDF | Manual entry**, with Excel active by default (the Excel file is the canonical source — PDF is just its print). The global "Confirm & Save / Clear" action bar is hidden when the Excel segment is active to avoid two competing buttons; Excel segment owns its own dedicated button now labelled **Confirm & Save batch →**. → `static/console.html`
- **[ui]** New **Auto-update →** button in the Excel segment with the same progress-bar pattern as the PDF version. Click → server picks the latest `.xlsx` from the watched `daily_packs` folder, parses, and renders the per-product preview + start-time suggestion + end-time prediction. User then clicks Confirm & Save batch. → `static/console.html`
- **[verify]** End-to-end live test: dropped `日報、各作業指示書２６.０４.２２.xlsx` into `auto_uploads/daily_packs/`. Auto-update found and parsed it (15 products, total 12,486 packs). Save wrote 15 rows to `daily_pack_items` AND upserted `daily_packs` row for 2026-04-22 with `number_of_packs=12486`; subsequent GETs of `/api/daily-packs/2026-04-22` and `/api/daily-packs/items/2026-04-22` both return correct data. → `main.py`, `static/console.html`

## 2026-04-28 — Daily Packs Excel parser: real-file layout (入力画面 sheet, fullwidth Ｎ/Ｙ, value-below-label)
- **[fix]** First Excel parser failed on real workbooks ("Could not find header row"). Real layout differs from the synthetic test sample: **入力画面** is the canonical input sheet (not the first sheet — workbook has 50+ sheets), header tokens use **fullwidth Ｎ/Ｙ** (`Ｎ便計`, `Ｙ便計`), header **spans 3 rows** (token row + 便 label row + region row), product names sit at column 2 with single-letter ID codes ("A", "B", …) at column 0, 製造日 is stored as **Excel serial date** (e.g. `46134` → 2026-04-22), and 入力者/天気/温度 values are **directly below** their labels rather than to the right. → `main.py`
- **[backend]** Rewrote `parse_daily_pack_excel` to a multi-sheet, NFKC-tolerant pipeline: tries `入力画面` then `受注集計表` then any other sheet containing the header pair. Anchors the header window on the row containing `N便計` (NFKC-folded) and extends 2 rows forward to capture batch-label and region-label rows. New helpers: `_xlsx_serial_to_date`, `_nfkc`, `_find_pack_header_window`, `_resolve_pack_columns`, `_split_region_cols`, `_value_near_label` (checks both right-of-label and below-label), `_scan_pack_meta`, `_is_product_name` (excludes single-letter IDs by requiring length ≥3 + at least one non-ASCII char + not in `_PACK_NOISE_NAMES` set). → `main.py`
- **[verify]** Live test against `/home/pi/DATA/UPLOAD/日報、各作業指示書２６.０４.２２.xlsx`: sheet=`入力画面`, header_row=4, all 15 products with 全合計 + 入り数 + six region×batch cells extracted. Meta: `production_date=2026-04-22`, `input_by=仁科`, `weather=曇り`, `temperature=23`. Auto-detected start 17:00 from 54 attendance records (median IN 16:09). Predicted end 23:16 for 12,486 packs at avg ~1,988 p/h. Smoke-tested across `２６.０１.０１`–`２６.０１.０６` (10 products each, all dates parsed correctly, all weather/temp/input_by extracted). → `main.py`

## 2026-04-28 — Daily Packs: Excel upload + per-product DB + production-rate editor + end-time prediction
- **[schema]** New `daily_pack_items` table (`init_db`). Columns: `batch_id`, `production_date`, `product_name`, `product_key` (NFKC-normalized for fuzzy match), six per-region/per-batch quantity columns (`n_yamanashi…y_matsumoto`), `n_total`, `y_total`, `grand_total`, `packs_per_case`, `rate_per_hour`, `est_seconds`, `source_filename`, `weather`, `temperature`, `input_by`, `start_time`, `end_time`, `uploaded_at`. Indexed on `production_date` and `batch_id`. The existing `daily_packs` summary table is untouched. Same-date re-upload deletes prior rows then re-inserts (overwrite semantics). → `main.py`
- **[backend]** New `production_rates.json` (per-product packs/hour + a `_default_rate_per_hour`). UI-editable. Endpoints: `GET /api/production-rates`, `POST /api/production-rates`. Lookups try exact name match first, then NFKC-normalized whitespace-stripped fallback so renames/spacing changes still hit the right product. Missing products fall back to default and are flagged in the UI. → `main.py`, `production_rates.json`
- **[backend]** Excel parser (`parse_daily_pack_excel`, openpyxl) handles the 日報・各作業指示書 sheet. Layout-tolerant: finds the header row by scanning for `N便計 / Y便計 / 全合計` text; resolves region columns by 山梨/長野/松本 labels (smaller column index = N便, larger = Y便); identifies each product row by its leftmost non-numeric cell; stops on 3 consecutive blank rows so the totals/store-count block is excluded. Picks up 製造日, 入力者, 天気, 温度 by label scan. → `main.py`
- **[backend]** Start-time auto-detect (`_suggest_start_time`): reads `attendance_records.commute_time` for the production date, computes the median IN time (with overnight 0–4h shifted to +24h), subtracts 30 min, snaps to whichever of **17:00 / 19:00** is closer. Returns `{start_time, source, median_in, n, candidates}` so the UI can surface "auto · median IN 16:32 (n=14)". Manual override always wins on save. → `main.py`
- **[backend]** End-time prediction (`_build_prediction`): per-product `seconds = grand_total / rate × 3600`, summed; `end_time = start + total_seconds`. Returns total quantity, total minutes, average packs/hour, and a per-product breakdown (`product_name, qty, rate_per_hour, rate_default, minutes`). Staffing-adjusted rate is left as a hook for later — `rate_per_hour` is persisted at save time so the formula can change without schema work. → `main.py`
- **[backend]** New endpoints: `POST /api/daily-packs/extract-excel` (multipart upload, returns parse + suggestion + prediction without touching DB), `POST /api/daily-packs/save-excel-batch` (overwrites same-date batch, inserts one row per product with `rate_per_hour` and `est_seconds` snapshotted), `GET /api/daily-packs/items/{date}` (read back). The start-time GET lives at `/api/daily-packs/start-time/suggest` to avoid colliding with the existing `/api/daily-packs/{record_date}` path-param route. → `main.py`
- **[ui]** Daily Packs tab gains a third segment **Upload Excel** alongside Manual entry / Upload PDF. New panel shows: file dropzone (.xlsx/.xlsm), parsed meta (date / input_by / weather), Start time selector (auto-populated by suggestion + manual override), live-recomputed Predicted end + Total qty, and a 13-column preview table (product / N合計 / Y合計 / 全合計 / 入り数 / Rate p/h / Min / six region×batch cells). Rows using a default rate are highlighted amber. Save batch button posts to the new endpoint and reports the resulting batch_id. → `static/console.html`
- **[ui]** Embedded **Production rates editor** (collapsible `<details>`) on the Daily Packs tab: lists every product known to `production_rates.json` plus any product from the current parse, lets the operator type a per-product rate, and saves to the JSON. Default-rate field at the top. Re-saving rates triggers a live re-prediction without needing to re-upload the Excel. → `static/console.html`
- **[verify]** End-to-end test: synthetic .xlsx with two products parsed cleanly — `meta.production_date` resolved from `26/04/2026`, both products extracted with `grand_total`, prediction `17:00 → 17:56` at avg 2,125 p/h. → `/tmp/test_pack.xlsx` (transient)

## 2026-04-28 — Admin Overview adopts /dashboard/ visuals + Refresh + Run-health-check
- **[ui]** Admin Overview tab rewritten to use `/api/status` (rich CPU/Memory/Disk/Swap/Load/Uptime + services) and `/api/temp` directly — fixes the "—" placeholders that came from `/admin/api/status`'s narrower `system` payload (only had `cpu_percent / ram_percent / ram_available_mb`). 6-card KPI grid + colored progress bars (good/warn/danger thresholds at 70/90%) mirror `/dashboard/` exactly. → `static/admin.html`
- **[ui]** New "Health monitor log" card (dark terminal style) reads `/api/maintenance/status` and shows last 30 entries reversed, color-classified (OK / ACTION / WARN / ERR). Status pill indicates `running` vs `ready` vs `no log` vs `unreachable`. → `static/admin.html`
- **[ui]** New "Services" panel with per-service mini CPU/RAM bars (matches dashboard's service-grid). → `static/admin.html`
- **[ui]** Action bar at top of Overview adds **↻ Refresh** (re-pulls everything) and **⚕ Run health check** (`POST /api/maintenance/run-health-monitor`, then polls the log for 10s so the new entries appear without manual refresh). → `static/admin.html`

## 2026-04-27 — /admin SPA redesign + configurable announcement banner + visitors/security tabs
- **[backend]** New configurable announcement system. `announcement.json` stores `{enabled, type, color, badge, text_en, text_ja, ends_at, dismissible, updated_at, presets}` with five presets (beta / maintenance / info / success / warning). Public `GET /api/announcement` (no auth — read by console banner) and admin-gated `POST /admin/api/announcement` (validates `color` against `{amber,red,blue,green,gray,purple}`, clamps text length). Replaces the previously hard-coded BETA banner. → `main.py`, `announcement.json`
- **[backend]** New `GET /admin/api/processes?top=N` returns `{by_cpu, by_mem, self}` from psutil — primes CPU%, sleeps 250ms, then samples again so values are real. Used for the Overview "this process / top tasks" cards. → `main.py`
- **[backend]** Visitors aggregation + IP labeling. `known_ips.json` stores `{ip: {label, owner, color}}`. New endpoints: `GET /admin/api/ip-labels`, `POST /admin/api/ip-labels` (set or delete), `GET /admin/api/visitors` aggregates the in-memory access ring per-IP into `{first_seen, last_seen, hits, errors_4xx, errors_5xx, devices, paths_unique, label?, owner?, color?}`. Admin can tag any IP "Office" / "Home" / "Buddhika" so the Access Log + Visitors + Alerts pages all colour-code requests. → `main.py`, `known_ips.json`
- **[backend]** Security signals endpoint `GET /admin/api/security` derives `hits_5m / 15m / 60m`, `top_ips_5m`, `top_4xx_60m`, and a `suspicious_paths` list filtered by `_SUSPICIOUS_PATH_HINTS` (`.env`, `/wp-`, `/.git`, `/phpmyadmin`, `/xmlrpc`, `/etc/passwd`, `/.aws`, `/admin.php`). Cheap heuristics from the existing access ring — no extra collection cost. → `main.py`
- **[ui]** `static/admin.html` rewritten as a single-page hash-routed SPA in the dashboard's light Space Grotesk theme (`--bg #edf3f6`, soft cards, `--brand #12618f`). Seven panels routed by `#/overview`, `#/access`, `#/visitors`, `#/alerts`, `#/security`, `#/announcement`, `#/bridge`. Active panel auto-refreshes every 8s. → `static/admin.html`
- **[ui]** Overview shows server health (CPU/MEM/disk/load/uptime), DB, auto-upload, masked API keys, **this process** (uvicorn pid/cpu/mem/threads/started), and **top CPU / top MEM** task tables.
- **[ui]** Access Log tab: live feed with filter input (matches IP or path), human-readable relative timestamps (`3m ago`, `yesterday 14:32`), per-row IP-label badge.
- **[ui]** Visitors tab: per-IP rows with **inline-editable** Label / Owner / Color fields (Save or Enter saves; × deletes), plus first/last seen, total hits, 4xx/5xx counts, devices. The "verify office vs me" feature.
- **[ui]** Alerts tab: standalone view of `NEW_LOGIN_ALERTS` with IP-label badges; warn-banner above the tabs auto-shows when `count > 0` so it's visible from any panel.
- **[ui]** Security tab: traffic windows, top IPs (5m), 4xx-heavy IPs (1h), suspicious-path probes — designed for spotting bot scans + abuse without flipping to Grafana.
- **[ui]** Announcement tab: form with preset picker (beta/maintenance/info/success/warning auto-fills color+badge+text), color/badge/text_en/text_ja/ends_at/enabled/dismissible fields, **live preview banner** matching the colour theme, and Save publishes to `announcement.json` instantly.
- **[ui]** `/attendance/console` banner replaced. New `<div id="annBanner">` reads `/attendance/api/announcement` on load + every 5 minutes. Six colour themes (amber/red/blue/green/gray/purple) mirror the admin presets. Dismissible per-browser via `localStorage["annDismissed:<updated_at>"]` — when admin publishes a new banner the new `updated_at` makes it re-appear automatically. A small "show notice" pill in the banner area lets the user bring back a dismissed banner without reloading. → `static/console.html`

## 2026-04-27 — Split watched folders (attendance vs daily_packs) + filter rename + Electron guide
- **[backend]** Watched-folder config split into two independent paths. New globals `AUTO_UPLOAD_DIR` (attendance) and `DAILY_PACKS_AUTO_UPLOAD_DIR` (daily packs). `auto_upload_config.json` schema migrated from flat `{path}` to `{attendance:{...}, daily_packs:{...}}` with backward-compat loader (`_load_split_config`) that auto-promotes legacy `path` → `attendance.path`. `_set_auto_upload_path(..., kind=...)` writes per-section history. `auto_extract_daily_packs` now reads from `DAILY_PACKS_AUTO_UPLOAD_DIR`, so attendance and pack PDFs no longer collide in one folder. → `main.py`, `auto_upload_config.json`
- **[backend]** New endpoints: `GET /api/auto-upload/config?kind=...`, `GET /api/auto-upload/config/all`, `POST /api/auto-upload/config` (now takes `kind`), and `GET /api/daily-packs/auto-upload/info` (parallel to the attendance variant). → `main.py`
- **[infra]** Disk layout: `auto_uploads/attendance/` (3 existing 就業日報 PDFs moved here) and `auto_uploads/daily_packs/` (new, empty). → `auto_uploads/{attendance,daily_packs}/`
- **[ui]** Renamed `Use latest from server →` → `Auto-update →` on both the Attendance PDF and Daily Packs tabs. → `static/console.html`
- **[ui]** Renamed upload-worktable filters and rewrote their semantics. `Missing leave only` → **Not recorded data** (IN xor OUT missing — data not received from the timeclock). `Overnight only` → **Absent** (neither IN nor OUT). Both unchecked = all names visible (default). Updated `isMissingLeave` / `isOvernight` helpers in console.html and index.html accordingly; aliases preserved so render code keeps working. Removed the default-checked state so all rows show on first load. → `static/console.html`, `index.html`
- **[docs]** New `API_APP_GUIDE.md`: split-folder server overview, the three API key labels (TEST / APP / WEB), CMD / PowerShell / curl recipes, full Electron skeleton (`package.json`, `main.js`, `preload.js`, `watch.js` with chokidar), `electron-builder` packaging, suggestions for what the desktop **Auto-update** button can do beyond the HTTP call (robocopy presync, auto-open Excel, toast on mismatch, auto-print, Slack webhook, archive copy, Task Scheduler), and a desktop-compatibility checklist for the existing web UI. → `API_APP_GUIDE.md`

## 2026-04-27 — Cross-page nav + watched-folder accepts single PDF + Windows-path detection
- **[ui]** Added Console / Gantt / Summary / Reports / Management nav links to all four entry pages so users can switch between them in one click. `static/console.html` topnav extended; `static/summary.html` topbar gets a Reports link; `static/gantt.html` toolbar gets a 4-link nav (Console / Gantt / Summary / Reports). Reports page already had the same nav from the previous change. → `static/console.html`, `static/summary.html`, `static/gantt.html`
- **[backend]** Watched-folder resolver now accepts either a directory of PDFs OR a single `.pdf` file path: new `_resolve_watched_target()` returns `(folder, single_file)` tuple, and `_pick_latest_pdf_in()` short-circuits to the file if the path is a single PDF. `attendance_auto_upload_info` returns `kind` ("file" / "folder" / "missing") and `is_windows_path` so the UI can render an accurate badge. `v1_pdf_upload` writes to `parent` when the configured path is itself a file. → `main.py`
- **[backend]** New `_looks_like_windows_path()` heuristic flags `E:\…` / `C:/…` / UNC paths. The auto-upload endpoint now returns a long, actionable 404 detail when a Windows-only path is configured, listing the two valid options (push via `/api/v1/pdf/upload` with X-API-Key, or mount via CIFS/SMB). Replaces the previous generic "Mount the Windows share" message. → `main.py`
- **[ui]** Watched-folder status badge in the Attendance PDF tab now reads the `info` endpoint and renders three distinct states: ✓ reachable (with file-vs-folder + PDF count), ⚠ Windows path warning (with inline HTML hint listing the two fixes), or ✗ not reachable. → `static/console.html`

## 2026-04-27 — Single-window console build: API keys, /admin panel, access tracking, settable auto-upload URL, reordered tabs, separate Reports page, /var/www/console/ CLI

- **[api]** Three named API keys (TEST / APP / WEB) auto-bootstrapped at first run into `attendance_app/api_keys.json` (chmod 600). Auth via `X-API-Key` header, validated with constant-time compare. New `require_api_key` FastAPI dependency returns the key label so handlers can log who called. → `main.py`
- **[api]** New structured `/api/v1/*` endpoints, all key-protected: `GET /ping`, `POST /pdf/upload` (multipart, writes into the watched folder), `GET /pdf/list`, `GET /pdf/retrieve/{filename}`, `POST /pdf/auto-upload?save=…` (delegates to existing auto-upload). Existing UI endpoints stay open (no key required). → `main.py`
- **[config]** Auto-upload watched-folder path is now settable + persisted in `attendance_app/auto_upload_config.json`. `_load_auto_upload_path()` reads the JSON first, falls back to env var, then to the historical default. New endpoints: `GET /api/auto-upload/config`, `POST /api/auto-upload/config` with body `{path, source}`. The previous path is rolled into `history[]` so changes are auditable. → `main.py`
- **[ui]** Tabs reordered to **フルキャスト → Attendance PDF → Daily Packs → Reports**. The active-by-default panel switched from Attendance PDF to フルキャスト. The "Reports" tab is now an `<a>` link to `/attendance/reports` rather than an in-page panel — Tab 4 contents extracted to a standalone page. → `static/console.html`
- **[ui]** Attendance PDF tab gains a "Watched folder (auto-upload source)" card with an editable URL/path input, "Save URL" + "Use latest →" buttons, and a live reachable/saved-at status line. The path persists per-machine and is shown immediately on every visit. → `static/console.html`
- **[ui]** New `static/reports.html` served at `/attendance/reports` (route added in `main.py`). Same layout as the old Tab 4 (Attendance Report card + Summarizing Report card + report-date picker driven by `/api/gantt/latest-date`), with header nav back to Console / Management / Logs. → `static/reports.html`, `main.py`
- **[admin]** New `/admin` panel served from inside attendance_app and proxied through nginx (`location /admin/ → 127.0.0.1:8002/admin/`). Cookie-session login gated by a single password in `attendance_app/admin_config.json`. Routes: `GET /admin` (login or panel), `POST /admin/login`, `POST /admin/logout`, `GET /admin/api/status`, `GET /admin/api/access-log`, `GET /admin/api/alerts`, `POST /admin/api/alerts/clear`, `GET /admin/api/api-keys` (masked). Panel shows server health (CPU/RAM/disk via existing `_sample_system_load`), DB connectivity, auto-upload state, masked API keys, full access log, new-login alerts, and an iframe bridge to `/upload/`. → `main.py`, `static/admin.html`, `static/admin_login.html`
- **[security]** New `AccessTrackingMiddleware` records every non-static request in a 500-entry in-memory ring + appends one JSON line per request to `/var/log/ai_server/access.jsonl` (falls back to `attendance_app/logs/access.jsonl` if `/var/log/ai_server` isn't writable). Each entry: timestamp, IP (X-Real-IP / X-Forwarded-For aware), parsed device label (browser + OS), method, path, status, duration_ms, sha256-truncated client fingerprint. First-time fingerprints are added to `known_clients.json` and emitted as a "new login" alert visible in the admin panel. → `main.py`
- **[infra]** New `location /admin/` block added to `/etc/nginx/sites-enabled/ai-server` (proxy_pass to 8002, X-Real-IP forwarding, 50M body limit). `nginx -t` clean, `systemctl reload nginx` green. Service `attendance.service` restarted; startup log confirms keys + admin config + auto-upload path loaded. → `/etc/nginx/sites-enabled/ai-server`
- **[cli]** New `/var/www/console/` directory: `api_client.py` (stdlib-only `ConsoleClient` with `ping/list_pdfs/upload_pdf/retrieve_pdf/auto_upload`), `console_cli.py` (argparse CLI with `ping|list|upload|get|auto`, reads `CONSOLE_BASE_URL` + `CONSOLE_API_KEY` from env), `README.md`. Marked executable. → `/var/www/console/{api_client.py, console_cli.py, README.md}`
- **[backup]** All five touched files snapshotted before edits to `/var/www/backups/console_build_20260427_143354/` (main.py, console.html, CHANGELOG.md, PROGRESS_BUG_STATUS.md, nginx_ai-server.conf). Stale `.bak` left in `sites-enabled` was caught by `nginx -t` and moved out before reload.

## 2026-04-25 — Management board: multi-select + multi-drag for employee cards
- **[ui]** `#board` employee cards now support multi-select. Plain click selects only that card (clicking the only-selected card again deselects). Ctrl/⌘-click toggles individual cards into/out of the selection; Shift-click selects a contiguous range across both sections in current board order. Selection state lives in `selectedCodes: Set<string>` plus `lastClickedCode` for shift anchoring. Cards in the selection get a `.selected` class (brand-tinted border + 2px ring). → `static/management.html`
- **[ui]** Drag now carries the whole selection. On `dragstart` for a selected card, `dragGroup` snapshots the selected codes in board order; for an unselected card the selection is reset to that one code so single-card drag behaviour is unchanged. When `dragGroup.length > 1`, a custom drag image (a brand-coloured pill reading "N employees") is set via `dataTransfer.setDragImage`. All cards in the group get `.dragging` opacity. → `static/management.html`
- **[ui]** Drop-on-card and drop-on-dept handlers were rewritten to splice every code in `dragGroup` out of `employees[]` (preserving relative order), apply section change + `pending=true` only to those that actually changed section, then re-insert as a contiguous block at the target position (before/after the target card based on Y position, or appended for dept-area drops). `event.stopPropagation()` was added to the card-drop handler so the dept-drop doesn't run a second time on the same drop. Drop on a card already inside `dragGroup` is a no-op (prevents self-move). → `static/management.html`
- **[ui]** Toolbar in `.board-tools` gains a `#selectionPill` ("No selection" / "N selected") and a `#clearSelBtn` "Clear selection" button. Clicking empty board space (anywhere outside a `.employee` card) clears the selection; Esc also clears. `applySelectionDisplay()` is called at the end of every `renderBoard()` so the highlight survives re-renders, and any codes that have been removed (e.g. via the × button) are pruned out of `selectedCodes` to keep the count accurate. → `static/management.html`
- **[i18n]** Added a bilingual help-list bullet ("Multi-select & drag many at once" / "複数選択してまとめて移動") explaining Ctrl/⌘-click, Shift-click, and group-drag. The selection pill and Clear button also have `data-i18n-en`/`data-i18n-ja` attributes so they translate with the existing `applyLang()` mechanism. → `static/management.html`

## 2026-04-25 — Management import: drag-and-drop + multi-PDF batch upload
- **[ui]** "Import from attendance PDF" panel gets a real drop zone (`#importDropzone`, repurposing the previously-orphan `.import-dropzone` class). The zone highlights on `dragover`, accepts dropped files, and is also clickable (it's a `<label for="importInput">`) so the existing "Choose PDF" button is now folded into the drop zone itself. → `static/management.html`
- **[ui]** `#importInput` now has `multiple`, so the user can pick (or drop) several PDFs at once. The change handler was replaced with `processPdfFiles()`, which filters for `.pdf` / `application/pdf`, then POSTs each file to `/api/management/import-pdf` sequentially (backend signature unchanged — still one file per call). Rows from every PDF are merged into `importRows`, deduped by employee code via a `Set`. Summary pill shows live progress ("Loading 2 / 5: foo.pdf"). → `static/management.html`
- **[ui]** New `#importFiles` chip strip below the drop zone shows one chip per PDF being processed: `loading…`, `→ N rows` (green) on success, or `error: HTTP …` (red) on failure. Hint message ends with `${total} unique rows loaded from N PDFs` and appends ` · K failed` when any file errored. The "Clear" button now also wipes the chip strip and resets the hint state. → `static/management.html`

## 2026-04-24 — KPI_CALCULATIONS.md: single-source spec for productivity KPIs
- **[docs]** New `KPI_CALCULATIONS.md` captures every formula used for daily and MTD productivity reporting: working-hours parser, per-section LP with target gaps (Sec1=85, Sec2=35, Combined=25 P/h), MTD aggregates, HR performance-score composite (attendance 50% + volume 50%, banded A–E), and data-accuracy definitions (days_no_record vs days_blank). Includes canonical SQL for the Section-2 per-employee MTD ranking and the per-section daily LP calculation so any future dashboard or report can hit the same numbers. → `KPI_CALCULATIONS.md`

## 2026-04-24 — Gantt: フルキャスト total-hours cell shows group total (not per-person)
- **[ui]** Temp-staff rows on the Gantt chart were rendering the per-person hours (`wh`) in the right-hand total cell, so a 7名 × 8h shift displayed as "8h" instead of "56h". The API already sends `total_hours` per row (= headcount × hours_per_person, line 1604) and the DB already stores it correctly (line 594), so only the render path needed fixing. For temp rows the total cell now reads `emp.total_hours`; regular employees continue to show their own shift hours. Bar length is unchanged — it still represents one person's shift. → `static/gantt.html`

## 2026-04-24 — Gantt: leave-time label always visible (narrow bars + early-start rows)
- **[ui]** Gantt chart now always shows the leave-time label for every clocked-in employee. Two cases were dropping the label: (1) employees clocking in before 10:00 (the chart window start) had their leave label suppressed by an `isMorning?'':outShown` branch, (2) short shifts (~<2h45m) produced a bar narrower than the 12% width threshold so the in-label took priority and the out-label was dropped. Fix: removed the `isMorning` suppression and lowered the in-bar threshold from `w>=12` to `w>=8`. → `static/gantt.html`
- **[ui]** For bars still too narrow to fit both labels inside (w<8%), the leave label is now rendered just to the right of the bar on `.track-wrap` (outside `.track` so it isn't clipped by `overflow:hidden`). The split-segment continuation (rendered with reduced opacity) is excluded from the outside label so overnight shifts don't show a duplicate. → `static/gantt.html`

## 2026-04-23 — BETA / test-mode banner + bilingual progress report
- **[ui]** Added BETA banner to both Console and Management pages: amber bar under the topbar with bilingual EN/JA message "This app is currently under test and data verification / 本アプリは現在テスト・データ検証中です。". Matches mobile breakpoint and uses the Industrial Futurism color palette. → `static/console.html`, `static/management.html`
- **[docs]** New `PROGRESS_BUG_STATUS.md` — non-technical, bilingual EN/JA summary of every bug found in testing and how it was fixed. Intended as a status hand-off document for management / stakeholders. No code, no file paths, only user-facing issue + resolution per item. → `PROGRESS_BUG_STATUS.md`

## 2026-04-23 — Daily Packs PDF: bulk upload speed-up + 504 timeout fix
- **[api]** `/api/daily-packs/extract-pdf` and `/api/daily-packs/extract-pdf-multi` no longer run the full attendance table parse (`parse_pdf_data`) or mismatch scan. Tab 3 only needs production date + pack count + フルキャスト rows + existing-data check, so skipping the heavy parse drops per-file processing from ~1s to ~0.37s. Mismatch fields remain in the response shape (always 0/empty) so no frontend break. → `main.py`
- **[ui]** Tab 3 upload flow now batches PDFs in groups of 8 (`PACK_BATCH_SIZE`), making one POST per batch instead of one giant POST. Each request stays well under Cloudflare's 100s gateway timeout even for 100+ PDFs. Progress message updates as each batch completes ("Extracting 24/100 PDF(s)…"). → `static/console.html`
- **[ui]** Confirm button is disabled and labelled "Extracting…" while the extract-multi calls are in flight, preventing the race where fast clicks produced "Upload PDF(s) first" even though a PDF was selected. Error messages now distinguish three cases: "Still extracting", "Drop or pick PDF(s) first", "Extraction did not return any data". → `static/console.html`

## 2026-04-23 — Daily Packs PDF: フルキャスト auto-extract + shift→prod date correction
- **[feature]** Uploading a production-summary PDF on Tab 3 now auto-extracts not only the pack count but also every `フルキャスト N 名 HH:MM HH:MM HH:MM` row. Each row is parsed into company / headcount / start / leave / overnight flag / hours, and shown in a preview table before save. PDF's third (hours) column is ignored because the source sometimes prints a wrong total (e.g. `47:15` for a 6h45m shift) — hours are recomputed from start + leave server-side. → `main.py`, `static/console.html`
- **[feature]** Preview shows per-date **Skip / Overwrite** radios for both Daily packs and フルキャスト sections when the DB already has data for that date — so existing rows are never replaced by accident. Overwrite replaces all フルキャスト rows for the date; Skip leaves them untouched. → `static/console.html`
- **[api]** New helpers `extract_fullcast_rows(full_text)`, `normalize_plus24_time(raw)` (converts `26:40` → `02:40` with `next_day=True`), `fetch_existing_daily_pack(date)`, `fetch_existing_temp_staff(date)`. → `main.py`
- **[api]** New helper `shift_to_prod_date(shift_date)` shifts the PDF's printed date (e.g. `2026年4月20日製造分`) forward by one day so the pack count and フルキャスト hours are saved under the correct production day. Response now carries both `shift_date` (raw PDF date) and `record_date` (save target). Comment in source explains how to change the offset if the business rule moves. → `main.py`
- **[ui]** Preview shows a grey muted note `PDF shift date 2026-04-20 → saving under prod date 2026-04-21 (+1 day)` when the two differ, so the user sees at a glance what's being saved. → `static/console.html`

## 2026-04-23 — Database reset for clean verification
- **[db]** Truncated `attendance_records` (19,357 rows), `upload_batches` (355 rows), `daily_packs` (96 rows), `temp_staff` (26 rows). Identity sequences reset to 1 so subsequent inserts start fresh. `employee_roster.json` was untouched (80 employees preserved). Done at user request prior to customer-facing test cycle. → DB only

## 2026-04-23 — Security & data-integrity fixes (XSS + negative numbers + shift-window limits)
- **[security]** **Stored XSS** on Management page: employee names like `<img src=x onerror=alert(1)>` were rendered unescaped in the roster grid. Closed with defence-in-depth — input validation (client), `esc()` helper wrapping every `innerHTML` insertion (render), and server-side name validation (max 100 chars, reject `< > " ' \` ; \\` and control chars) in `PUT /api/management/roster`. `employee_roster.json` scanned and confirmed clean. → `static/management.html`, `main.py`
- **[bug]** **Negative numbers accepted** — `フルキャスト` headcount could be set to -5 (→ -35 total hours); Daily Packs could be set to -9999. Added 3-layer clamps: browser input event + submit-time check + backend `hours_per_person <= 0` rejection. → `static/console.html`, `main.py`
- **[ui/logic]** **Tab 2 shift-window constraint** — start-time must be 18:00–22:00, leave-time at or before next-day 10:00, total ≤ 16 hours. Out-of-range rows are outlined red and cannot be submitted. Prevents the earlier case where user could enter e.g. 07:00 start and the backward-chosen leave computed impossible hours. New constants at top of file (`SHIFT_START_MIN`, `SHIFT_START_MAX`, `SHIFT_LEAVE_NEXT_DAY_MAX`, `SHIFT_MAX_HOURS`) + `validateShiftRow(div)` function. → `static/console.html`
- **[db/api]** **Overnight support in temp_staff** — new `leave_next_day BOOLEAN NOT NULL DEFAULT FALSE` column. Replaces the brittle `leave_h <= 6` heuristic in `calculate_temp_staff_hours` with an explicit flag. Back-filled 4 existing rows (id 22/23/67/69) with corrected hours using Postgres EPOCH arithmetic (21.05h, 7.82h, 15.08h, 7.75h). `GET /api/temp-staff/{date}` + `POST /api/temp-staff` now round-trip the flag; Gantt read encodes overnight leave as `+24` notation to match `attendance_records.time_to_leave` convention. Tab 2 auto-sets the flag when leave ≤ start and shows a `翌日` badge on the leave-time input. → `main.py`, `static/console.html`
- **[bug]** **Date display off by one day before 09:00 JST** — `toISO(d)` was using `toISOString()` which converts local JST to UTC, so dates rendered as the previous day during early-morning hours. Replaced with local `getFullYear() / getMonth() / getDate()` accessors. Affected `shiftDateForNow()`, `productionDateForNow()`, Tab 2/3/4 auto-dates, and the top-right live clock. → `static/console.html`

## 2026-04-21 — Management GUI mockup on dev branch
- **[ui]** Added `/management` as a locked User Management mockup with demo password `admin2026`, five department columns, drag-to-reassign employee cards, `+ Add employee`, remove buttons, unsaved-change indicator, Save/Reset controls, and Lock. Save is intentionally browser-only until backend approval. → `static/management.html`, `main.py`
- **[ui]** Replaced the old top nav in the console with clean links: Upload, Management, Dashboard ↗ (`/grafana/`), and Console ↗ (`rnd.asiakawaii.com`). → `static/console.html`
- **[docs]** Documented the new management mockup entry point. → `README.md`

## 2026-04-21 — V3 attendance console naming refresh
- **[docs]** Renamed the project-facing title from Attendance Operations Console to **V3 Attendance Console** and documented the `/attendance/console`, `/attendance/gantt`, and `/attendance/summary` entry points. → `README.md`, `CHANGELOG.md`
- **[ui/api]** Updated visible page titles, brand labels, footer copy, and FastAPI metadata to match the V3 console name. → `index.html`, `static/console.html`, `main.py`

## 2026-04-21 — Summary PDF → B3 landscape · 3-month demo-data seeder
- **[print]** Summary page `PDF` button now outputs **B3 landscape (353 × 500 mm)** instead of A4. Wider page lets the combined chart, 4-block comparisons grid, and the 14-day daily breakdown table all sit side-by-side without column truncation. Slightly larger base font (12px) and card padding in print context so numbers read cleanly on B3. → `static/summary.html`
- **[tooling]** New `seed_demo_data.py` — generates 3 months of *realistic* demo data in the DB for dashboard demonstrations. Uses the real `employee_roster.json` + `sections.json` so every row is tied to an existing employee and section.
  - Pattern matches real ops: Mon–Fri full staff (92–98% present, 8.0–9.5 hr shifts with OT tail), Saturday partial (30–45% of staff, 4–5 hr), Sunday + approximate JP holidays skipped. Per-employee start-time/hours profile is stable across the run (same person has consistent habits).
  - Pack counts are back-solved from the S1 target: `packs ≈ LP_S1 × s1_hours`, where `LP_S1 ~ N(85, 6²)` with day-of-week intensity (Mon +8%, Fri -6%) and month-end push. That automatically produces S2 LP in the 35–50 range and Combined LP in the 24–32 range — i.e. the same "S1 near target, S2 overshoots, Combined slightly above" shape you see in real data.
  - Adds a `フルキャスト` temp-staff bucket (3–7 workers) on ~30% of weekdays so the gantt view also shows the 派遣 row.
  - Safe-to-rerun: every row is marked with `file_name LIKE 'DEMO-SEED-%'` / `note='demo'`, so `--replace` only wipes demo rows and never touches real uploads.
  - Usage: `python3 seed_demo_data.py --start 2026-01-21 --end 2026-04-21 --replace` (or `--dry-run` to preview totals/averages first).
  - Dry-run against 2026-01-21 → 2026-04-21 produced 75 workdays, 1,140,169 packs total, avg LP S1=79.8 / S2=43.8 / Combined=28.2 — right where the targets sit. → `seed_demo_data.py`

## 2026-04-21 — Summary page (`/attendance/summary`) with target-line KPIs
- **[feature]** **New summary dashboard** at `GET /summary` → `static/summary.html`. Whole-operation productivity view next to per-section breakdown, with all the comparison angles asked for in one page.
  - **Range selector** (pills): Day / Week / Month / 3 Month. End-date picker (defaults to latest date with data from `/api/gantt/latest-date`). Two toggles: *Compare vs previous period* and *Show target lines*.
  - **KPI cards**: 4 tiles — S1 LP, S2 LP, Combined LP, total Packs. Each LP tile shows current value, delta-vs-previous-period badge (▲/▼/–/n/a), and a target-vs-actual progress bar hitting `S1=85`, `S2=35`, `Combined=25` P/h (as requested). Packs tile shows period total plus delta.
  - **Combined SVG chart** (single chart, as requested): three LP lines (S1=blue, S2=orange, Combined=purple) + optional packs bars on a secondary axis + three dashed target lines at 85/35/25 + dashed previous-period lines when compare is on. Interactive crosshair + tooltip (date, weekday JA 日月火水木金土, LP per section, % of target, delta). Legend items are click-to-toggle.
  - **Comparisons grid** (4 blocks): (1) **Day-over-day** — latest day vs prior day. (2) **Same weekday** — latest day vs same weekday one week back (Friday vs previous Friday, etc.). (3) **Period aggregate** — current range total/avg vs previous equal-length range. (4) **Best / Worst days** — highest-LP and lowest-LP days inside the current range.
  - **14-day breakdown table**: Date · Weekday · Packs · S1 Hrs/LP/%tgt · S2 Hrs/LP/%tgt · Combined Hrs/LP/%tgt. `%tgt` pills color-coded (≥100% green, 85–99% amber, <85% red).
  - **Targets are editable in one place** (top of JS): `const TARGETS = {s1:85, s2:35, combined:25, packs:null};` — change here and every card / chart line / table pill updates.
  - **Responsive + print**: desktop wide, tablet 2-col, phone single-col; `@media print` forces A4 landscape for PDF export button.
  - **API reuse**: pulls from existing `/api/productivity?range=…&end=…` (which already returns `{current, previous}` with `{labels, packs, hours_s1/s2/combined, lp_s1/s2/combined}`) — no new backend endpoints needed.
  - **Nav**: topbar adds Summary link next to Console / Gantt. → `main.py`, `static/summary.html`

## 2026-04-21 — Shift/Prod formula fix · Daily Packs DB sync · フルキャスト in Section 2
- **[ui/logic]** **Shift / Production date formula** rewritten around the real 10:00 → next-day 08:30 cycle:
  - `shiftDateForNow()`: `hour < 10` → yesterday, else today.
  - `productionDateForNow()`: **always `shiftDate + 1 day`** (prior rule used `hour >= 19` → tomorrow, which was wrong during 00:00–09:59 and during the 08:30–10:00 "gap"). Verified against 20 test times including month/year rollovers.
  - Example — now = `2026/04/21 10:33:56` → Shift=`2026-04-21`, Prod=`2026-04-22`. Example — now = `2026/04/22 00:00:00` → Shift=`2026-04-21`, Prod=`2026-04-22` (still inside the cycle that started 10:00 on 04/21).
  - Applies everywhere: top-right live clock, Tab 2 auto-date, Tab 3 auto-date, Tab 4 report-date fallback.
  - Hint text under each date input updated to reflect the real rule.
  → `static/console.html`
- **[bug]** **Daily Packs DB sync was broken** — UI read `j.found` but the backend returns `j.exists`, so the saved pack count never appeared. Fixed field name; also added cache-busting to the GET call, pre-fill of the count + note inputs, and a re-load after Confirm so the "updated_at" stamp refreshes. POST is still an upsert, so re-Confirming the same date overwrites the old row with the new value — the "update if value changed" path is now fully round-tripped through the UI. → `static/console.html`
- **[api]** **`GET /api/gantt/{date}` now includes フルキャスト/temp-staff** as synthetic rows at the **end of 製造２課**. Each saved `temp_staff` entry becomes one row with:
  - code `TEMP-{id}`, name `{company} × {headcount}名`, bar spanning `start_time → leave_time`, `wh` = per-person hours (so bar length matches one worker's shift).
  - `is_temp: true`, `headcount`, `total_hours` so the productivity math can fold the group into Section 2.
  - Section 2 productivity totals now include group `total_hours` (= headcount × hours_per_person) and add each headcount to `staff_present` / `staff_total`.
  - Response gains a `productivity.temp_staff = {headcount, total_hours, total_hours_hhmm, row_count}` block so the UI can surface "includes N temp-staff hours" if desired. → `main.py`
- **[ui]** **Gantt highlights temp-staff rows** with orange `#c7701b` bars (matching the S2 accent), a `派遣 ·` prefix in the name-cell, and a new legend entry `派遣 · Temp staff (フルキャスト)`. Row count replaces the employee code (`5名` instead of `TEMP-12`). → `static/gantt.html`

## 2026-04-21 — Dual time labels + responsive layout + previous-day delta arrows
- **[ui]** Next-day leave label inside each bar now shows **both formats**: the 24+ continuous-axis time and the actual clock time — e.g. `28:00 / 04:00` (midnight exactly → `24:00 / 00:00`). Keeps the timeline continuous while making the real wall-clock leave obvious for ops. New `fmtOutTimeDual(inH,outH,outStr)` helper; `paintSeg` auto-falls-back to the short form (just `28:00`) when the bar is <18% wide. Applies to PDF output as well (same template). → `static/gantt.html`
- **[ui]** Screen view now **fits the viewport** instead of being locked to A4:
  - Desktop / monitor: `.page{width:min(calc(100vw - 24px), 1400px)}` so wide screens get a wide report.
  - Phone (≤600px): tighter padding + smaller base font.
  - Tablet (≤900px): existing responsive rules kept (full-width page, 2-col summary, narrower name cell).
  - Print (`@media print`): still locked to A4 portrait (`.page{width:210mm; margin:0;}`).
  Embed mode (`?embed=1`) still renders at 100% width for the iframe.
  → `static/gantt.html`
- **[ui]** Productivity panel cards now show a **previous-day comparison badge** in the top-right corner of each card:
  - Green `▲ +x.x%` when the value went up.
  - Red `▼ -x.x%` when it went down.
  - Gray `– 0.0%` when flat (change <0.5%).
  - Neutral `— n/a` when no prior-day data exists.
  Badge is absolutely positioned (`.p-delta`) so it never reflows title/number. `.p-tag` gets `padding-right:64px` (52px in print) to reserve space for the badge. Tooltip shows the previous value (`vs 2026-04-20: 12,436`). → `static/gantt.html`
- **[api]** `GET /api/gantt/{record_date}` now computes productivity for **both the current date and the previous day** and emits `productivity.previous_date` + `productivity.previous = {total_packs, sections, combined}`. Shared `_gantt_compute_for_date(cursor, date, roster_index)` helper (extracted from the endpoint) handles both calls; delta math is client-side so no extra round trips. 400 Bad Request if `record_date` isn't `YYYY-MM-DD`. → `main.py`

## 2026-04-21 — Gantt report works for every date (cache + graceful fallback)
- **[fix]** `/gantt` and `/console` now respond with `Cache-Control: no-store` so browsers always receive the latest template after a redesign — no more "only 2026-04-17 shows the new layout because that's the tab I had open when the service restarted". → `main.py`
- **[fix]** Frontend `load(date)` now fetches `api/gantt/{date}?_=<timestamp>` with `cache:'no-store'`, so even if a proxy caches GETs, every date-switch pulls fresh data. → `static/gantt.html`
- **[ui]** Productivity panel renders for **every date**:
  - Missing pack count → big number shows `—` and hint reads `Pack count not saved yet for YYYY-MM-DD` in red.
  - Missing productivity object (older backend) → client-side fallback computes section hours/staff from row data so the panel never shows raw "0 / N" scard boxes.
  - LP values use `—` instead of `0.00 P/h` when pack count or hours are zero. → `static/gantt.html`

## 2026-04-21 — Attendance Report redesign (window, in-bar labels, productivity panel)
- **[ui]** Gantt window moved from `14:00 → 07:00` to `10:00 → 08:30 next day` (22.5 h span). Header meta text and axis ticks follow automatically from `WIN_START`/`WIN_HOURS`. → `static/gantt.html`
- **[ui]** Both start and leave times now render **inside** the colored bar (flex space-between) — leave time is no longer on a separate row below the track. `.label-row`, `.label-spacer`, `.label-track`, `.under-lbl` CSS and markup retired. → `static/gantt.html`
- **[ui]** Next-day leave times display in 24+ format (e.g. `04:00` → `28:00`) via new `fmtOutTime(inH,outH,outStr)` helper, so a shift that clocks out after midnight reads as a continuous time axis. `toMN` case (exact midnight) shows `24:00`. → `static/gantt.html`
- **[ui]** Top 4-card summary replaced with a 4-card **Productivity panel** (bilingual, attractive, print-friendly):
  1. **製造パック数 · Packs Manufactured** — total output e.g. `12,436 P`
  2. **製造１課 人時生産性 · S1 Labor Productivity** — `P/h` + hours HH:MM + staff count
  3. **製造２課 人時生産性 · S2 Labor Productivity** — `P/h` + hours HH:MM + staff count
  4. **人時生産性計算　合計 · Combined Labor Productivity** — `P/h` + total hours HH:MM
  Each card uses a left accent stripe, gradient fill, and colored pill tag (TOTAL / S1 / S2). → `static/gantt.html`
- **[api]** `GET /api/gantt/{record_date}` now:
  - Sorts rows **by `EMPLOYEE_ROSTER` index** (authoritative order from `employee_roster.json`) inside each section bucket, so updating the JSON is the single way to reorder all downstream outputs.
  - Fetches `daily_packs.number_of_packs` for the date.
  - Emits a new `productivity` object: `{total_packs, sections: [{id,label,staff_present,staff_total,total_hours,total_hours_hhmm,lp}], combined: {staff_present,total_hours,total_hours_hhmm,lp}}`.
  - Adds `_wh_to_hours`, `_hours_to_hhmm` helpers; LP = total_packs / hours.
  → `main.py`
- **[ui]** Print CSS tightened: `@page margin 4mm`, page padding `3mm 4mm`, body font `10px`, bar height `12px`, smaller headers/gaps — target 1–2 pages A4 portrait. → `static/gantt.html`
- **[docs]** Confirmed `employee_roster.json` is the **single source of truth** for ordering across all pipelines (PDF parsing via `apply_employee_roster`, DB export, Excel export, Gantt display, Productivity report). Updating the JSON and restarting the service propagates the new order everywhere; adding a new entry immediately makes that employee visible in all outputs once data flows in.

## 2026-04-21 — Attendance Gantt "no data" bugfix
- **[bug]** Gantt page for 2026-04-17 rendered 70 employee rows all as "absent / empty track" even though `/api/gantt/2026-04-17` returned full data. Root cause: API field `wh` was `"9:25 hr"` (with trailing ` hr`), and frontend `parseWH` did `split(':').map(Number)` → `[9, NaN]` → `h + NaN/60 = NaN` → every row classified as absent.
- **[fix]** Backend `/api/gantt/{date}` now strips trailing `hr/hrs/h./HR` from `working_hours` before emitting (`_clean_wh` helper). Response field `wh` is plain `H:MM`. → `main.py`
- **[fix]** Frontend `parseWH` + `parseH` hardened to tolerate any trailing `hr/hrs/h` and return `0`/`null` on bad input instead of `NaN`. → `static/gantt.html`

## 2026-04-21 — auto-upload button removed from UI
- **[ui]** Removed `自動取込` button, status pill, path display, and the `refreshAutoUploadInfo()` JS from Tab 1. Folder is not reachable from the Pi, so the UI was showing `folder not found` with nothing actionable. Also removed the `.auto-upload-row` CSS. → `static/console.html`
- **[api]** Endpoints `POST /api/attendance/auto-upload` and `GET /api/attendance/auto-upload/info` remain registered and usable once a Pi-side inbox folder is wired (Samba mount of the Windows share, or a local sync inbox at `ATTENDANCE_AUTO_UPLOAD_DIR`). No backend changes. → `main.py`

## 2026-04-21 — console cleanup + auto-upload hardening
- **[ui]** Removed leftover `.console-hero` CSS block entirely. Hero section was already gone from markup; the class definitions are now also gone. → `static/console.html`
- **[ui]** Topbar switched from flex to `grid-template-columns: auto 1fr auto` so the live clock always sits on the far right at desktop width. At ≤900px it drops onto a second row alongside the brand. Clock is no longer a child of `.topnav`. → `static/console.html`
- **[ui]** Auto-upload row now shows a status pill (`checking… / N PDF ready / folder empty / folder not found / info endpoint offline`) plus the latest filename, so folder state is always visible without clicking. → `static/console.html`
- **[api]** `GET /api/attendance/auto-upload/info` now returns `{ path, exists, pdf_count, latest_filename, env_override }`. → `main.py`
- **[ops]** Boot-time log line `[AUTO_UPLOAD] watched folder = … (exists=…)` so `journalctl -u attendance.service` confirms registration and path. → `main.py`

## 2026-04-21 — v3.0 console hero/clock/auto-upload/date
- **[ui]** Removed the `v3.0 · FUSION TEST / Operations Console` intro card; tab bar is now the first card. → `static/console.html`
- **[ui]** Added live clock widget in the top-right corner: current time + date, plus computed **Shift date** and **Production date** (ticks every second, uses existing tab rules). → `static/console.html`
- **[ui]** Added `⚡ 自動取込` button in Tab 1: pulls latest PDF from a hardcoded watched folder, auto-previews, Confirm saves without re-upload. → `static/console.html`
- **[api]** `extract_pdf_metadata` now prefers `処理日：YYYY/MM/DD` (fullwidth/ASCII colon, `/`, `／`, `-`, `.`, `年月` separators) and falls back to the existing `YYYY年MM月DD日`. Drives the green banner date and the Tab 4 Report date. → `main.py`
- **[api]** New `GET /api/attendance/auto-upload/info`, new `POST /api/attendance/auto-upload?save=bool`. Configurable via env var `ATTENDANCE_AUTO_UPLOAD_DIR`; default `/mnt/windows_share/Buddhika/Desktop/人時生産性　PDF`. → `main.py`

## 2026-04-20 — Tab 2 backend + tab-sync rules
- **[db]** New `temp_staff` table (record_date, company, headcount, start/leave, hours_per_person, total_hours, note). → `main.py`
- **[api]** `GET /api/temp-staff/{date}` + `POST /api/temp-staff` (delete-then-insert bulk for a date; server computes overnight-aware hours). → `main.py`
- **[ui]** Tab 2 (フルキャスト): Shift date defaults via `shiftDateForNow()` (yesterday if hour<12). Changing the date reloads saved rows from DB. Add row / live totals / Confirm POSTs + advances to Tab 3. → `static/console.html`
- **[ui]** Tab 3 (Daily Packs): renamed "Record date" → "Production date". Auto = today, or tomorrow if hour≥19. DB-sync on date change. → `static/console.html`
- **[ui]** Tab 4 (Reports): Report date defaults to the working-day date of the last PDF uploaded this session; falls back to `/api/gantt/latest-date`. Summarizing Report opens `/summary?date=…` in a new tab (page still pending). → `static/console.html`

## 2026-04-19 — v3.0 console first cut
- **[ui]** New `/attendance/console` single-page GUI with four tabs (Attendance PDF, フルキャスト, Daily Packs, Reports), theme matched to the existing dashboard. → `static/console.html`
- **[api]** `GET /console` route serves `static/console.html`. → `main.py`

---

_Notes for future updates:_
- Prepend new entries at the top; never rewrite history.
- Tag area in brackets: `[ui] [api] [db] [ops] [docs]`.
- If a change is user-visible, include the user-facing name (e.g. "Shift date rule", "auto-upload button").
