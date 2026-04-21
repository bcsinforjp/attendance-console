# Attendance Gantt — Integration Plan

Compact A4-portrait Gantt wired to the live DB, mounted in the
"Processing protection and optimization" section of the attendance app.

## Design rules
- Axis ticks every **2h** (14,16,18,20,22,00,02,04,06)
- Narrow margins (6mm), row height 12px, name col 100px
- Tabs per section (製造1課 / 製造2課) — extensible to N sections
- Single theme: matches existing attendance app styling
- **Low code, low tokens** — reuse existing DOM/fetch patterns, no new deps

## Stages

### Stage 1 — Backend endpoint
New route: `GET /api/gantt/{record_date}` → returns
```json
{ "date":"2026-03-28",
  "sections":[
    {"id":1,"label":"製造1課","rows":[{code,name,in,out,wh}, ...]},
    {"id":2,"label":"製造2課","rows":[...]}
  ]}
```
- Read rows from `attendance_records` where `record_date = :date`
- Join `employee_roster.json` to get section mapping
- Fallback: if roster has no section → "Unassigned" tab

**Touches:** [main.py](main.py), [employee_roster.json](employee_roster.json)

### Stage 2 — Section mapping ✅ DONE
Created [sections.json](sections.json) with code→section mapping.
Minimal shape (no names — DB is authoritative for `full_name`).
Any code absent from sections.json goes to "Unassigned" tab.

- 製造１課 (id=1): 25 codes
- 製造２課 (id=2): 45 codes
- Total: 70 codes

**Touches:** [sections.json](sections.json)

### Stage 3 — Compact Gantt component
Extract the rendering logic from `attendance_gantt.html` into
[static/gantt.js](static/gantt.js) + [static/gantt.css](static/gantt.css):
- `renderGantt(container, data)` — pure fn, takes API response
- A4 portrait print rules (`@page size:A4 portrait; margin:6mm`)
- 2h axis ticks, compact row height, tab bar at top for sections
- No hard-coded data — all from API

**Touches:** new `static/gantt.js`, `static/gantt.css`

### Stage 4 — Embed in index.html
Inject a Gantt panel under the "Processing protection and optimization"
block (around line 1177). Includes:
- Date picker (defaults to latest `record_date` in DB)
- "Open full page ↗" button → opens `/attendance/gantt?date=YYYY-MM-DD`
- Inline compact chart (same component as Stage 3)

**Touches:** [index.html](index.html)

### Stage 5 — Standalone full-page view
New route: `GET /gantt` → serves [static/gantt_page.html](static/gantt_page.html)
which uses the same `gantt.js` + `gantt.css`.
- Opens in a new tab with `?date=…`
- "⬇ Download PDF" button fires `window.print()` (A4 portrait)
- Same compact layout as the embedded view

**Touches:** new `static/gantt_page.html`, route in [main.py](main.py)

## Build order ✅ ALL DONE
1. Stage 2 — sections.json ✅
2. Stage 1 — `/api/gantt/{date}` + `/api/gantt/latest-date` ✅
3. Stage 3 + 5 — single [static/gantt.html](static/gantt.html), served by `/gantt` ✅
4. Stage 4 — panel embedded in [index.html](index.html) below Processing Protection ✅

Service restarted via `sudo systemctl restart attendance.service`.
Verified: /api/gantt/2026-04-01 returns 25+45 rows across 2 sections.
