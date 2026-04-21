# Changelog — V3 Attendance Console

Live log of every change made to the app. Newest on top.
I update this file on every edit so it can drive the project changelog.

Format: `YYYY-MM-DD — [area] what changed (why) → files`

---

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
