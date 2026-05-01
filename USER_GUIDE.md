# V3 Attendance Console — Operator User Guide

**Version:** 3.5 (post-tag work on `dev`)
**Live:** https://rnd.asiakawaii.com/attendance/
**Last updated:** 2026-05-01

This is the day-to-day guide for the operator. It walks through the full
shift workflow from PDF upload → daily-packs Excel → フルキャスト → reports →
LINE delivery, plus the admin tools (Roster, Day-off, Cleanup).

> 🇯🇵 Bilingual snippets (EN / 日本語) appear throughout. The system itself
> is bilingual on every page.

---

## 1. The four daily dates — memorise this once

Every screen lines up around four dates that **all relate to each other**:

| Date | What it is | Equation |
|---|---|---|
| **Attendance PDF date** | Day printed on the attendance PDF | the date the shift workers actually clocked in |
| **Shift date** | Date used by フルキャスト 手動入力 + temp_staff DB | **= attendance PDF date** (same calendar day) |
| **Production date** | Date on the daily-packs Excel | **= shift date + 1** |
| **Report date** | Date the Reports / Gantt / Summary page asks for | **= production date** |

So:

```
attendance PDF (2026-04-18)
  ↓ +1 day
shift date / フルキャスト (2026-04-18) ← yes, same as PDF date
  ↓ +1 day
production date / report date / Daily Packs Excel (2026-04-19)
```

> **Why:** the night shift starts at ~19:00 on day D and finishes at ~08:30
> on day D+1. The packs are booked to D+1; the workers' attendance is
> booked to D.

---

## 2. Top navigation — same on every page

Every page has the same green-tinted top bar:

```
🌐 Dashboard  Console  Gantt  Summary  Reports  Management   [API healthy]   [live clock]
```

- **🌐 Dashboard** — under construction (placeholder for the future live ops dashboard).
- **Console** — daily input pipeline (PDF, フルキャスト, Daily Packs).
- **Gantt** — per-day employee timeline (the print layout).
- **Summary** — productivity trend (rolling N-day chart with target lines).
- **Reports** — read-only launcher; opens individual reports in popup windows.
- **Management** — admin: roster, day-off schedule, LINE recipients, data cleanup.
- **API healthy / clock / Shift / Prod** — live status pills (auto-update every 60s / every second).

The top nav is **hidden** when a page is opened in report-popup mode
(`?report=1`) so the popup view stays focused.

---

## 3. Daily workflow — the normal end-of-shift path

### 3.1 Upload the attendance PDF

**Console → 1 Upload tab.**

Drop the day's `就業日報YYYY.MM.DD.pdf` onto the upload area, or use the desktop
client (`upload_latest.bat pdf`). Once uploaded, click **Auto-update →**.

Behind the scenes:
- The PDF lands in `auto_uploads/attendance/`.
- The server parses every employee row and writes them to
  `attendance_records` keyed on the **PDF date** (= shift date).
- If a file with the same date was already there, the older copy is
  removed (one-file-per-day rule).

### 3.2 Daily Packs Excel — Auto-update + Confirm & Save

**Console → 3 Daily Packs tab → Excel sub-segment.**

Drop the day's `夜勤用日報YYYY.MM.DD.xlsm` (or use `upload_latest.bat xlsx`),
then click **Auto-update →**. Three preview blocks appear:

1. **SECTION 2 TOTALS** strip — shows `Ｎ合計 / Ｙ合計 / 合計` from the
   right side of `入力画面`. Auto cross-checks against per-product `N+Y`
   sum; warns only when the difference is > 0.5%.
2. **フルキャスト** card — auto-extracted from `人時生産性` rows R78-R79
   (or the equivalent rows for your file). Shows `5 名 + 3 名 = 8 名 ·
   75.0h total` plus per-row times (e.g. `19:00 → 翌 04:00`). A **Skip**
   checkbox lets you opt out — the existing `temp_staff` rows for that
   date are then left alone.
3. **製造予定表 A/B/C lines** — three colour-coded cards (S1 blue, S2
   green, S3 orange) with item × planned × N × Y × start.
   The **start time pill** at the top shows the canonical start (= the
   latest first-item start across A/B/C, e.g. 19:20).

Adjust the **Start time** (auto-suggested from the production plan) if needed
— **End time** is auto-computed at run-end + **30 min buffer**. Click
**Confirm & Save batch →**.

### 3.3 What gets saved (one transaction)

| Table | Rows |
|---|---|
| `daily_pack_items` | One per product (replaces the date's previous batch) |
| `daily_packs` | Day-level row with `number_of_packs`, `n_total`, `y_total`, `section_start_time` |
| `temp_staff` | One row per フルキャスト bucket (skipped if **Skip** is checked) — keyed on **shift date** (= production_date − 1) |
| `production_plan` | One row per (date, line, item) for the A / B / C plan |

### 3.4 Where you land after save

| Entry point | Lands on |
|---|---|
| Daily Packs → Excel → Confirm & Save batch → | **Reports** (`/reports?date=production_date`) |
| Daily Packs → Manual → Confirm & Save → | **Reports** (`/reports?date=production_date`) |
| **2 フルキャスト tab → ⚡ Auto-update from Excel** | back on **2 フルキャスト**, with `fcDate = shift_date` and the saved 会社 / 人数 rows visible |

---

## 4. フルキャスト 手動入力 (manual entry tab)

**Console → 2 フルキャスト tab.**

For days when there's no Excel yet, or when you want to edit the
auto-extracted rows.

Per-row fields: `会社` (company, default `フルキャスト`) / `人数`
(headcount) / `開始` (start) / `退出` (leave).

Three action buttons:
- **+ Add row** — manual bucket.
- **⚡ Auto-update from Excel** — runs the entire Daily Packs Excel
  flow (auto-update → save) and lands you back here on `shift_date`
  with the auto-extracted rows visible. **One click for the whole loop.**
- **Skip →** — confirms there are no フルキャスト for this shift and
  jumps to Daily Packs without writing anything.

The **shift date** at the top auto-resolves: today before 10:00 → yesterday
(still inside the prior cycle); 10:00 onward → today. Selecting a date
reloads saved rows from the database.

---

## 5. Reports → LINE delivery

**Reports tab.**

Two cards: **Attendance Report** and **Summarizing Report**. Pick a date
(defaults to the latest data date in DB), click **📂 Open Report ↗** on the
card you want — opens the report in a popup window.

The popup lets you:
- Print
- **💬 Send to LINE** → sends a styled card to every registered LINE
  recipient. The card has:
  - Branded thumbnail image (`attendance_card.jpg` or `summary_card.jpg`)
  - Title `勤怠記録 · Attendance Report` (or `月次サマリー · Monthly Summary`)
  - Date line `📅 YYYY-MM-DD　タップで詳細を表示`
  - Single tap button **📊 View Report** (or **📈 View Summary**)
  - Tapping anywhere on the card opens `/m/report?date=…` (or `/m/summary?date=…`)

> The LINE flow is **locked** — don't change endpoints, message types, or
> tap targets without explicit operator approval.

### How recipients get registered

1. The recipient adds the LINE bot as a friend (QR code on LINE Developers
   Console → Messaging API tab).
2. They send any message to the bot.
3. The webhook auto-registers them and replies with their userId.
4. From Management → 💬 LINE Recipients you can rename them
   (e.g. `creator`, `factory_manager`) or remove them.
5. From then on, every Send-to-LINE click reaches them.

---

## 6. Mobile viewer pages

Same graphics as `/gantt` and `/summary` but with the admin chrome hidden,
so they're optimised for the recipient's phone:

- `https://rnd.asiakawaii.com/attendance/m/report?date=YYYY-MM-DD` — gantt view, mobile-trimmed (no Member Hours tab, no Print/PDF buttons). `/m/gantt` is an alias for `/m/report`.
- `https://rnd.asiakawaii.com/attendance/m/summary?date=YYYY-MM-DD` — productivity trend chart. **Tap the chart → fullscreen rotated view**, with Close (✕) and Re-rotate (↻) buttons, plus tap-to-show tooltip that works in both portrait and landscape modes.

---

## 7. Management page — five admin tabs

`/management` (password-locked).

### 7.1 📋 Roster · 名簿管理

The existing employee management board:
- Drag & drop to move people between 製造1課 / 製造2課.
- Reorder within a section by dragging.
- Multi-select with Ctrl/⌘ + Shift, drag the group together.
- Bulk-add employees from an attendance PDF.
- Manual `+ Add employee`.
- Search across code / name / section.
- Save / Reset / Lock buttons in the page-local toolbar.

### 7.2 📅 Day-off Schedule · 休暇予定表

Plan everyone's day-offs in a grid.

**Section sub-tabs**: 製造1課 / 製造2課, default 製造2課.

**Date range** with three presets:
- **📆 This cycle (21–20)** — the 21st-of-month → 20th-of-next-month fiscal cycle (default).
- **Calendar month** — 1st–end-of-month.
- **Next 30 days** — rolling.

**Six summary rows** above the editable grid:
- 出勤 · Present (count)
- 休 · Off (count)
- 休率 · Off % (colour-graded: ≥30% red, ≥15% amber)
- 人時 · P/h (per-day section P/h)
- 前日比 · vs prev (▲/▼ Δ% vs previous day)
- 対目標 · vs target (▲/▼ % vs S1=85 / S2=35)

**Tap a cell → toggles "OFF"** (orange pill). Save / Reset enable when
the draft differs from the saved baseline.

**📤 Import 定休表 (.xlsx)** — uploads the yearly 定休表 spreadsheet,
matches Excel nicknames (often surname-only / katakana shortform) against
the roster, shows a mapping wizard with auto-suggestions, and persists the
nickname → employee_code mapping to `nickname_map.json` so future imports
auto-resolve.

**🚨 Highlight unauthorized absence on report** — toggle near the Save
button. When ON: gantt views (desktop, mobile, popup) render absent
employees in red **🚨 Unauthorized** if their absence is NOT in the saved
day-off list. Absences that ARE in the list always render as a calm
green **休 scheduled** pill regardless of the toggle.

### 7.3 💬 LINE Recipients · LINE 通知先

One row per registered recipient (auto-populated by the LINE webhook).
Inline ✎ Rename (max 60 chars) and ✕ Remove buttons. Plus a global
**💬 Send Hi (test)** button to verify deliverability without sending a
real report.

### 7.4 🗑 Data Cleanup · データ削除

Two destructive operations, both with three safety rails:
- **Specific dates only** — no "delete all" / "wipe table" mode.
- **31 dates per operation maximum** (was 5; expanded for demo/testing).
- **Two-step confirm** — preview shows row counts per (table × date),
  big red bilingual warning panel appears, consent checkbox enables the
  red Delete button.

#### 7.4.a Per-date row deletion

Two ways to add dates:
- **`+ Add to list`** — single date picker; one date added per click.
- **From + To + `+ Add range`** — picks every day in the inclusive range
  in one click. Capped at 31 days per operation.

For each selected date, removes rows from:
`attendance_records` · `daily_packs` · `daily_pack_items` · `temp_staff` ·
`production_plan` (one transaction).

#### 7.4.b 📦 Old uploaded files (retention sweep)

Two scoping modes:
- **Threshold (days)** — default 30. Files older than this whose date's
  data is in the DB are flagged safe to delete.
- **From + To range** — when both are set, ignores the threshold and
  considers only files whose date is inside the range. Useful for
  "clean up files for a specific week" operations.

Click **🔍 Scan**. Both watched folders (`attendance` + `daily_packs`) are
listed with each file tagged:
- 🗑 `safe to delete` — eligible (in scope AND its date's data is in DB)
- ⚠ `old but no DB data — kept` — eligible by date but DB has nothing,
  so nothing is deleted (operator can still reprocess)
- `kept` — out of scope / recent

The Delete button removes only the safe-to-delete files. Server re-runs
the safety check on the delete call so a stale UI list can't trick it.

---

### 7.5 💬 Feedback · ご意見

Read-only viewer of all feedback received via the floating 💬 button.
Threshold input (1–500, default 50) + Refresh button; cards-per-entry
list with name / UTC timestamp / page path / IP / full multiline message.
Submissions still come from the FAB on every page — there's no "submit
feedback" form on this tab itself.

To read submissions outside the UI:

```bash
# Live tail
tail -f /var/www/attendance_app/logs/feedback.txt

# Pretty-print recent N entries via the API
curl 'https://rnd.asiakawaii.com/attendance/api/feedback/recent?limit=20' | jq .
```

---

## 7.6 💬 Floating Feedback button (FAB)

Small green pill in the bottom-right corner of every full page that
loads `site_header.js`. Click → a polished modal opens:

- **Sticky header** with title + ✕ close button.
- **Your name** (optional, max 60 chars).
- **Message** (required, max 4,000 chars). Live character counter turns
  amber at 3,000 and red at 3,900. **Ctrl/⌘ + Enter** sends.
- **`📍 /current/page`** line so you see exactly which page the message
  is being sent from.
- Cancel / 📨 Send. Esc / outside-click also closes.

Each submission is appended to `attendance_app/logs/feedback.txt` as one
JSON line (`ts`, `ip`, `name`, `page`, `ua`, `message`).

Endpoints:
- `POST /api/feedback` — body `{message, name?, page?}` (4 KB cap)
- `GET /api/feedback/recent?limit=N` (1..500) — newest first

| Surface | FAB visible? |
|---|:-:|
| Console / Gantt / Summary / Reports / Dashboard / Management | ✓ |
| Mobile viewers (`/m/report`, `/m/summary`) | — |
| Report popups (`?report=1`) | — |
| Print | — |

> The 🚧 demo-preview banner that previously sat above the page content
> has been removed in both its global form and its Management-scoped
> form. The FAB is now the only feedback surface. Use Management →
> 💬 Feedback to read submissions.

---

## 8. Data-status check

`GET /api/data-status/<YYYY-MM-DD>` (browser-facing) returns a quick
"is everything saved for this date?" answer:

```json
{
  "report_date": "2026-04-19",
  "shift_date":  "2026-04-18",
  "all_present": true,
  "missing": [],
  "blocks": {
    "attendance":      { "lookup_date": "2026-04-18", "rows": 156, "present": true  },
    "daily_packs":     { "lookup_date": "2026-04-19", "rows_summary": 1, "rows_items": 16, "present": true },
    "fullcast":        { "lookup_date": "2026-04-18", "rows": 2,   "present": true  },
    "production_plan": { "lookup_date": "2026-04-19", "rows": 17,  "present": true  }
  }
}
```

`missing` lists which kinds have no rows. Use this before triggering a
report-generation flow so you can warn the operator if something hasn't
been ingested yet.

---

## 9. Desktop client — `upload_latest.bat`

Bundled in the repo. Two subroutines, one CLI flag:

```cmd
upload_latest.bat              :: both flows (default)
upload_latest.bat pdf          :: attendance PDF flow only
upload_latest.bat xlsx         :: daily-packs Excel flow only
```

Watched folders (relative to the .bat):
```
.\watch\pdf\    ← attendance PDFs (.pdf)
.\watch\xlsx\   ← daily-packs Excel (.xlsx / .xlsm)
```

First run creates a `config.txt` — paste your API key, set the BASE URL,
re-run. The batch handles `curl` setup, logging to `upload_log.txt`,
schtasks recipes for daily / weekly automation.

Schedule examples (no admin needed):
```cmd
:: Daily 09:00 — both flows
schtasks /create /tn AttendanceUpload     /tr "\"%~dp0upload_latest.bat\""        /sc daily /st 09:00 /f
:: Daily 09:00 — PDF only
schtasks /create /tn AttendanceUploadPDF  /tr "\"%~dp0upload_latest.bat\" pdf"   /sc daily /st 09:00 /f
:: Daily 09:30 — Excel only
schtasks /create /tn AttendanceUploadXLSX /tr "\"%~dp0upload_latest.bat\" xlsx"  /sc daily /st 09:30 /f
```

---

## 10. Troubleshooting cheatsheet

| Symptom | Likely cause | Fix |
|---|---|---|
| LINE Verify in Developers Console returns 404 | Webhook URL typo / "Use webhook" toggle is OFF | URL must be `https://rnd.asiakawaii.com/attendance/api/line/webhook`; toggle ON in Developers Console **and** ensure auto-reply / greeting OFF in `manager.line.biz` |
| Send-to-LINE says "no recipients yet" | No-one has friended + messaged the bot | Recipient must add the bot via QR + send any message; webhook auto-registers them |
| Excel save shows `number_of_packs: 0` | Per-product 全合計 column blank in this workbook | Check that the right-side Ｎ合計 / Ｙ合計 are filled — they auto-override `number_of_packs` |
| Gantt shows red "🚨 Unauthorized" everywhere | Day-off schedule isn't loaded | Management → Day-off → import the yearly 定休表 .xlsx, then toggle highlight back on |
| `/m/report` URL 404 | Path typo (or the gantt URL not the mobile alias) | Use `/m/report` or `/m/gantt` (alias). Both work |
| Mobile chart reads small | Phone is in portrait | Tap the chart → enters fullscreen rotated landscape; ✕ closes |
| File piling up in watched folder | Same date re-uploaded under a different name | Older same-date files are auto-deleted on upload now (one-file-per-day). Manual sweep: Management → 🗑 Data Cleanup → 📦 Old uploaded files |

---

## 11. Where to look for what

| What | Where |
|---|---|
| Code — server entrypoint | `attendance_app/main.py` |
| Code — pages | `attendance_app/static/*.html` |
| Code — shared header | `attendance_app/static/site_header.js` |
| Config — admin password | `attendance_app/admin_config.json` (gitignored) |
| Config — LINE bot creds | `attendance_app/line_config.json` (gitignored) |
| Config — API keys | `attendance_app/api_keys.json` (gitignored) |
| Data — day-off schedule | `attendance_app/dayoff_schedule.json` (gitignored) |
| Data — Excel nickname mappings | `attendance_app/nickname_map.json` (gitignored) |
| Branded card images | `attendance_app/static/line_card_default/{attendance,summary}_card.jpg` |
| API reference | `attendance_app/API_APP_GUIDE.md` |
| Architecture / design notes | `attendance_app/PROJECT_INSIDE_AI_BLUEPRINT.md` |
| Detailed change log | `attendance_app/CHANGELOG.md` |
| Bilingual progress notes | `attendance_app/PROGRESS_BUG_STATUS.md` |
| **This guide** | `attendance_app/USER_GUIDE.md` |
