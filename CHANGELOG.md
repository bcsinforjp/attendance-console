# Changelog — V3 Attendance Console

Live log of every change made to the app. Newest on top.
I update this file on every edit so it can drive the project changelog.

Format: `YYYY-MM-DD — [area] what changed (why) → files`

---

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
