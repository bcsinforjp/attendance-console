# V3 Attendance Console — v3.3

Live app:

https://rnd.asiakawaii.com/attendance/

This project is a FastAPI-based V3 attendance console, PDF converter, and dashboard.
It uploads attendance PDFs, parses rostered employee rows, previews extracted data in the browser, exports Excel files, stores records in PostgreSQL, and serves dashboard APIs for reporting.

## What this app does

- Upload one PDF or multiple PDFs
- Run the `/attendance/console` v3 workflow for attendance PDFs, temp staff, daily packs, and reports
- Preview extracted attendance rows
- Convert attendance PDFs into Excel files
- Preserve the master employee roster order
- Insert special section text in the Excel export when required
- Save converted attendance records to PostgreSQL
- Serve summary and employee dashboard APIs
- Provide a plain-text employee-code endpoint for automation
- **(v3.2)** Push attendance reports to LINE — webhook auto-registers recipients who message the bot; the Gantt page renders a PDF in the browser and the server sends a tap-to-open link to all recipients
- **(v3.3)** Unified site header on every page; new `🌐 Dashboard` placeholder tab; Reports is a read-only popup launcher with `?report=1` flag that hides the top nav for focused viewing; Management page reorganised into 3 tabs (📋 Roster · 📅 Day-off Schedule · 💬 LINE Recipients) with a new day-off grid persisted to `dayoff_schedule.json`

## Main files

- Backend: `main.py`
- Frontend: `index.html`
- V3 console: `static/console.html`
- Employee roster: `employee_roster.json`
- AI blueprint for agents: `PROJECT_INSIDE_AI_BLUEPRINT.md`

## Live link

- Production web app: [https://rnd.asiakawaii.com/attendance/](https://rnd.asiakawaii.com/attendance/)

## How to use the app

1. Open the live link above.
2. Upload one or more attendance PDFs.
3. Click `Preview Data` to inspect parsed rows.
4. Review the table, filters, and row counts.
5. Click `Convert and Download` to generate the Excel file.
6. Save the downloaded `.xlsx` or `.zip` file.

## API shortcuts

- Health check: `/attendance/api/health`
- V3 console: `/attendance/console`
- User management mockup: `/attendance/management`
- Gantt report: `/attendance/gantt`
- Summary report: `/attendance/summary`
- Preview one file: `/attendance/api/preview`
- Preview many files: `/attendance/api/preview-multiple`
- Convert one file: `/attendance/api/convert`
- Convert many files: `/attendance/api/convert-multiple`
- Plain-text roster codes: `/attendance/api/roster/codes`

Example plain-text request:

```text
/attendance/api/roster/codes?code=00000326&code=00000401
```

Example response:

```text
00000326
00000401
```

## Excel export behavior

The Excel export keeps the roster order and includes the special section text between these two rows:

- `00000326`
- `00000401`

Inserted label:

```text
Section Two 2 Depanment
```

This label is part of the Excel output only.

## Local development

The app is served by FastAPI and runs through the systemd service `attendance.service`.

Typical backend command:

```bash
/var/www/attendance_app/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8002
```

Restart the service after backend edits:

```bash
sudo -n systemctl restart attendance.service
systemctl is-active attendance.service
```

## GitHub workflow

This repository is connected to:

```text
https://github.com/bcsinforjp/Attendance_web-app
```

Useful commands:

```bash
git -C /var/www/attendance_app status --short --branch
git -C /var/www/attendance_app add .
git -C /var/www/attendance_app commit -m "Describe change"
git -C /var/www/attendance_app push
```

## For AI agents

If you are a coding agent such as Codex, Cline, Claude, or Cursor:

- Read `PROJECT_INSIDE_AI_BLUEPRINT.md` first.
- Treat `main.py` as the backend source of truth.
- Treat `index.html` as the frontend source of truth.
- Preserve the roster order in `employee_roster.json`.
- Validate the exact behavior after every change.
- Update the blueprint if you change app behavior.

## Notes

- The app is optimized for the `/attendance/` path.
- The project uses PostgreSQL for saved attendance records.
- Runtime files such as SQLite databases and `__pycache__` are ignored by git.
