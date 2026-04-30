# AI Blueprint: Attendance Operations Console

## Purpose

This file is an AI-readable project blueprint for `/var/www/attendance_app`.
It is written as a working prompt/spec for coding agents such as Codex, Cline, Claude, Cursor, or any other autonomous editor.

Use this blueprint to:

- understand the current system quickly
- make safe updates without breaking live behavior
- preserve business rules and formatting constraints
- validate changes before handing work back

If this file conflicts with the live code, treat the live code as the source of truth and update this file afterward.

---

## Project Identity

- Project name: Attendance Operations Console
- Live path: `https://rnd.asiakawaii.com/attendance/`
- App version: **3.4** (FastAPI `app.version` in `main.py`)
- App type: FastAPI backend + single-file HTML/CSS/JS frontend
- Primary job:
  - upload Japanese attendance PDFs
  - parse attendance rows
  - align output to the master employee roster
  - preview data in-browser
  - export Excel files
  - store attendance records in PostgreSQL
  - provide dashboard APIs for reporting
  - **(v3.2)** push reports to LINE — webhook self-registers
    recipients, browser-rendered PDFs are uploaded back and pushed
    to all recipients as tap-to-open links

### Day-off Schedule (v3.3+, post-tag work on `dev`)

- File: `dayoff_schedule.json` (chmod-friendly atomic write, `_DAYOFF_LOCK`, **gitignored**). Shape:
  ```json
  {
    "schedule": { "<employee_code>": ["YYYY-MM-DD", ...] },
    "updated_at": "ISO-8601",
    "highlight_unauthorized": false
  }
  ```
- File: `nickname_map.json` (gitignored). One-way map from Excel nickname → 8-digit employee code, populated by the import wizard. Subsequent imports auto-resolve previously-mapped names.
- Endpoints (all under `/api/dayoff/`):
  - `GET /schedule` — returns the schedule + the toggle flag.
  - `PUT /schedule` — replaces schedule (validates dates, drops unknown codes, preserves the toggle).
  - `POST /highlight-unauthorized` — body `{enabled: bool}`, flips the toggle without touching the schedule.
  - `POST /import-excel` — multipart `file` (.xlsx, ≤25 MB, magic-byte `PK\x03\x04`). Skips `初期設定`. Iterates row 5+ on every monthly sheet, picks names from column 11+ unless they match a built-in 30-entry header blocklist. Resolves each name via (1) saved nickname map, (2) exact normalized match against `EMPLOYEE_ROSTER`. Returns matched + unmatched arrays; each unmatched entry has up to 8 substring-based roster suggestions.
  - `POST /apply-import` — body `{entries:[{code,date}], mappings:{nickname:code}, mode:"merge"|"replace_range"}`. Persists mappings to `nickname_map.json`, then folds entries into `dayoff_schedule.json`.
- Frontend lives on **Management → 📅 Day-off Schedule**. Section sub-tabs (📋 製造1課 / 📋 製造2課, default = 製造2課); 21-to-20 fiscal-cycle preset; the grid has employees as rows, dates as columns; the **6 summary rows** above the data are 出勤 / 休 / 休 % / 人時 P/h / 前日比 / 対目標 (the latter three are read from the `/api/m/summary` rolling endpoint and compared against `DO_TARGETS = {s1:85, s2:35, combined:25}`).
- The **🚨 Highlight unauthorized absence** toggle next to the Save button drives a global setting. The gantt page (`/gantt`, `/m/report`, popup `?report=1`) fetches `/api/dayoff/schedule` on every load; when an employee row classifies as `absent`:
  - If the date is in their day-off list → calm green `休 scheduled` pill (always, regardless of toggle);
  - Else if the toggle is ON → red `🚨 Unauthorized` row + tinted background + left border;
  - Else → faint "Absent" label (existing behaviour).
- Targets file is the single source of truth in [summary.html](attendance_app/static/summary.html) (`const TARGETS`); changes there must also be mirrored in `DO_TARGETS` inside [management.html](attendance_app/static/management.html).

### LINE integration (v3.2)

- Credentials live in `line_config.json` (chmod 600, gitignored).
- Endpoints (all under `/api/line/`): `webhook` (LINE → us; verifies
  `X-Line-Signature`, registers `userId`/`groupId`/`roomId`),
  `send` (browser → us → LINE; pushes a report-page URL),
  `upload-and-send` (multipart PDF upload → saved under
  `static/line_pdfs/<type>_<date>.pdf` → push URL),
  `test-hi` and `recipients` (helpers for the Reports page).
- LINE Developers Console webhook URL:
  `https://rnd.asiakawaii.com/attendance/api/line/webhook`.
- Auto-reply / Greeting messages must stay **OFF** in
  `manager.line.biz`, otherwise the LINE platform intercepts user
  messages before they reach the webhook.

---

## Authoritative Files

- Backend entrypoint: `/var/www/attendance_app/main.py`
- Frontend page: `/var/www/attendance_app/index.html`
- Master employee roster: `/var/www/attendance_app/employee_roster.json`
- Python environment: `/var/www/attendance_app/venv`
- Systemd service: `/etc/systemd/system/attendance.service`

There is no git repository currently initialized inside `/var/www/attendance_app`.
Do not assume git is available for rollback or history.

---

## Runtime Topology

### Service

- Service name: `attendance.service`
- Working directory: `/var/www/attendance_app`
- Startup command:

```bash
/var/www/attendance_app/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8002
```

### Web routing

- Nginx proxies `/attendance/` to the FastAPI app on port `8002`
- The frontend is served by FastAPI at `/`
- The frontend is subpath-aware and prefixes API calls with `/attendance` when needed

### Temporary file storage

- Uploaded PDFs: `/tmp/attendance_uploads`
- Exported files: `/tmp/attendance_exports`

### Database

- Engine: PostgreSQL
- Default host: `127.0.0.1`
- Default port: `5432`
- Default DB name: `attendance_db`
- Default user: `attendance`
- Default password: `attendance2026`

These defaults are read from environment variables in `main.py` if overridden.

---

## Core Business Rules

### PDF parsing

- PDF uploads must be non-empty and contain `%PDF` near the file start
- Only `.pdf` files are accepted
- Table parsing uses `pdfplumber`
- A valid attendance table is identified by a row containing `個人`
- Employee rows are recognized only when the employee code is exactly 8 digits

### Roster alignment

- Parsed rows are not exported as-is
- Output is rebuilt in the exact order of `employee_roster.json`
- If a roster employee is missing from the PDF, the output still contains that employee with blank values

### Time normalization

- Blank markers include values like `__:_`, `__:__`, `----`, `------`, `早退`
- Leave times after midnight are normalized into 24+ hour format
- Example:
  - `翌 1:00` becomes `25:00`
  - leave times at or before `6:59` may also be treated as next-day leave

### Working hours

- Working hours are calculated from normalized commute and leave times
- Standard output format is `H:MM hr`
- Dashboard code also tolerates legacy values without ` hr`

### Persistence

- Converted records are stored in PostgreSQL
- Upload batches are also stored
- Dashboard APIs read from PostgreSQL, not directly from uploaded files

---

## Current Special Output Rules

These rules are easy to break if an agent refactors without checking business intent.

### 1. Plain text roster-code endpoint

Endpoint:

```text
/api/roster/codes
```

Behavior:

- Returns `text/plain`
- Accepts repeated `code` query parameters
- Also supports comma-separated or whitespace-separated values inside `code`
- Returns only matching employee codes
- Preserves request order
- Response is one code per line

Example:

```text
/api/roster/codes?code=00000326&code=00000401
```

Expected response:

```text
00000326
00000401
```

### 2. Excel section label insertion

Current Excel export behavior includes a manual inserted row between these two employee rows:

- after `00000326`
- before `00000401`

Inserted label:

```text
Section Two 2 Depanment
```

Important:

- This inserted row is for Excel export only
- It does not change the plain text roster-code endpoint
- It does not change the roster JSON
- It should not affect the employee count shown in the summary row

Constants in `main.py`:

- `EXCEL_SECTION_INSERT_AFTER`
- `EXCEL_SECTION_INSERT_BEFORE`
- `EXCEL_SECTION_LABEL`

If business asks to change this wording later, update those constants and re-verify exported workbook structure.

---

## Backend Structure

All backend logic currently lives in `main.py`.

### Important functions

- `get_db_connection()`
  - opens PostgreSQL connection

- `init_db()`
  - creates `upload_batches` and `attendance_records` tables
  - creates useful indexes

- `normalize_time_value()`
  - normalizes attendance times
  - handles `翌` and overnight logic

- `calculate_working_hours()`
  - computes `H:MM hr`

- `parse_pdf_data(file_path)`
  - extracts rows from PDF tables
  - returns parsed attendance records only

- `apply_employee_roster(records)`
  - rebuilds output in master roster order

- `create_excel_file(records, filename)`
  - creates workbook
  - writes title, headers, data rows, inserted section row, and summary row

- `list_attendance_rows(month)`
  - reads persisted records for dashboard APIs

- `parse_requested_codes(raw_values)`
  - parses repeated/comma/newline-separated `code` inputs for plain-text endpoint

### Main API routes

- `GET /`
  - serves `index.html`

- `GET /api/health`
  - service/database health

- `GET /api/roster/codes`
  - plain text employee-code output

- `POST /api/preview`
  - preview one PDF

- `POST /api/preview-multiple`
  - preview many PDFs

- `POST /api/convert`
  - convert one PDF to Excel

- `POST /api/convert-multiple`
  - convert many PDFs into one zip bundle

- `GET /api/download/{filename}`
  - download `.xlsx` or `.zip`

- `GET /api/dashboard/summary`
- `GET /api/dashboard/employees`
- `GET /api/dashboard/employee/{employee_code}`
- `GET /api/dashboard/months`

### Data model expectations

Attendance record shape usually looks like:

```json
{
  "employee_code": "00000326",
  "name": "Employee Name",
  "commute_time": "18:51",
  "leave_time": "24:00",
  "working_hours": "5:09 hr"
}
```

---

## Frontend Structure

The frontend is a single self-contained `index.html` with:

- layout and visual styling
- upload interaction
- file validation
- preview table
- search, filter, sort, pagination
- convert-and-download flow
- API health indicator

### Frontend behavior notes

- The app is optimized for Raspberry Pi and low-power browsers
- API URLs are constructed through helper functions that respect the `/attendance` subpath
- Preview uses JSON APIs only
- Conversion triggers download by creating a temporary anchor element
- Current frontend does not directly expose the plain text roster-code endpoint

### Important frontend functions

- `getApiUrl(path)`
- `getDownloadUrl(path)`
- `validateIncomingFiles(files)`
- `runPreview()`
- `runConvert()`
- `renderTable()`
- `checkHealth()`

---

## Excel Export Rules

When changing Excel generation, preserve these expectations unless business explicitly asks otherwise:

- Worksheet title is `勤務表`
- Cell `A1` contains a dated title and spans `A1:E1`
- Header row is at row `3`
- Data rows begin at row `4`
- Export columns are:
  - personal code
  - name
  - commute time
  - leave time
  - working hours
- Summary row appears below the actual rendered data block
- Summary employee count should reflect actual employee records, not inserted label rows
- The inserted section label row must remain between `00000326` and `00000401`

If you refactor `create_excel_file()`, verify the row order in a generated workbook, not just the code.

---

## Database Expectations

### Tables

- `upload_batches`
- `attendance_records`

### `attendance_records` columns

- `upload_date`
- `file_name`
- `personal_code`
- `full_name`
- `commute_time`
- `time_to_leave`
- `working_hours`
- `record_date`
- `month_year`
- `created_at`

### Dashboard assumptions

- Dashboard summary APIs rely on `month_year`
- Latest month is chosen by latest saved batch if no month is provided
- Employee dashboard output is roster-aware for ordering

---

## Safe Change Protocol For AI Agents

When making changes, follow this sequence.

### 1. Read before editing

Always inspect:

- `/var/www/attendance_app/main.py`
- `/var/www/attendance_app/index.html`
- `/var/www/attendance_app/employee_roster.json` if employee ordering matters

### 2. Preserve live behavior

Before changing code, identify whether the request affects:

- parsing
- roster order
- Excel output
- plain-text output
- dashboard queries
- frontend rendering

Do not assume one layer controls the final output. This project has separate behaviors for:

- preview JSON
- Excel export
- dashboard APIs
- plain-text roster output

### 3. Keep edits small and local

Prefer minimal changes over broad refactors unless asked.

High-risk areas:

- time normalization
- employee roster ordering
- Excel row placement
- endpoint response format
- subpath-aware frontend URL logic

### 4. Restart service after backend changes

Use:

```bash
sudo -n systemctl restart attendance.service
systemctl is-active attendance.service
```

### 5. Validate the exact affected behavior

Examples:

- For API changes:

```bash
curl -s http://127.0.0.1:8002/api/health
curl -s "http://127.0.0.1:8002/api/roster/codes?code=00000326&code=00000401"
```

- For public path validation:

```bash
curl -s "https://rnd.asiakawaii.com/attendance/api/roster/codes?code=00000326&code=00000401"
```

- For Excel changes:
  - generate a workbook locally with the venv python
  - inspect row contents using `openpyxl`
  - confirm inserted text and row order

### 6. Update this blueprint if behavior changed

Any time an endpoint, workflow, or business rule changes, update `AI_BLUEPRINT.md`.

---

## Known Constraints And Risks

- No local git repo is present in `/var/www/attendance_app`
- Service restart may require `sudo -n`
- The project is live; changes affect production immediately after restart
- Frontend and backend are tightly coupled but not modularized
- `main.py` contains many responsibilities in one file, so broad refactors are risky
- Dashboard logic tolerates some older data formatting, so output normalization changes can have historical impact

---

## Recommended Future Improvements

These are optional and should only be done if requested.

- split `main.py` into parser, export, persistence, and API modules
- add automated regression tests for:
  - overnight leave normalization
  - roster alignment
  - plain-text roster-code endpoint formatting
  - Excel inserted section row placement
- move hard-coded business rules into configuration
- add a dedicated README for human operators
- add workbook snapshot tests for critical export layouts

---

## Quick Agent Prompt

If you are an AI agent opening this project for the first time, use this as your operating instruction:

1. Read `main.py`, `index.html`, and this blueprint.
2. Treat `employee_roster.json` as authoritative for employee order.
3. Preserve all current live behaviors unless the request explicitly changes them.
4. Be careful with the distinction between preview JSON, Excel output, dashboard APIs, and plain-text output.
5. If changing backend code, restart `attendance.service`.
6. Validate the exact user-requested behavior with local or public curl checks.
7. If you change business behavior, update this blueprint in the same task.

---

## Last Known Live Notes

At the time this blueprint was created:

- `/api/roster/codes` returns matching employee codes as plain text
- Excel export inserts `Section Two 2 Depanment` between `00000326` and `00000401`
- The live service is `attendance.service`
- The app is served from the `/attendance/` subpath through Nginx
