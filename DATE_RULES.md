# DATE_RULES.md

> Where every uploaded file's date ends up in the database — for **every upload method** (web manual, desktop agent, auto-upload).
>
> If a date number looks wrong anywhere in the app, the answer is on this page.
> **Change a rule by editing [`date_service.py`](date_service.py) only — never patch the same rule in two places.**

---

## 1. The one rule you have to remember

> **Report date is the anchor.** Everything else is derived from it.

```
                       ┌────────────────────────┐
                       │    REPORT DATE         │
                       │  (what you see at      │
                       │   the top of a report) │
                       └────────────┬───────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            │                       │                       │
            ▼                       ▼                       ▼
   Pack date = Report      Production = Report      Shift / PDF = Report − 1
   (daily_packs            (daily_pack_items,       (attendance_records,
    .record_date)           production_plan)         temp_staff
                                                     .record_date)
```

In words:

- **Pack date     = Report date**  (same day)
- **Production    = Report date**  (same day — just a different name)
- **Shift / PDF   = Report date − 1**  (one day earlier)

The UI also shows this as a small fixed label: when you open *Report 2026-04-11*, the page shows the shift date `2026-04-10` (= report − 1) so you know which attendance day the report is reading from.

---

### URL convention

`/gantt?date=YYYY-MM-DD` and `/api/gantt/{YYYY-MM-DD}` — the date in the URL is the **report date**. The server transparently subtracts 1 day when fetching `attendance_records` and `temp_staff`, and uses it as-is for `daily_packs` / `daily_pack_items`. So one URL fetches both halves of the same logical day of work.

LINE messages emit the same convention: `📋 Attendance Report 2026-04-08\nhttps://…/gantt?date=2026-04-08`.

---

## 2. The user's example — Report **2026-04-11**

You open **Attendance Report 2026-04-11** in the UI. Where does its data come from?

```
                     Report date  =  2026-04-11
                          │
       ┌──────────────────┼──────────────────┐
       │                  │                  │
       ▼                  ▼                  ▼
   PDF 2026.04.10.pdf   Excel 4/11        daily_packs
   (= report − 1)       (= report)         row keyed 2026-04-11
       │                  │
       ▼                  ▼
   attendance_records   daily_pack_items
   .record_date          .production_date
   = 2026-04-10          = 2026-04-11
```

| What the report fetches             | SQL                                                      | Date filter |
| ----------------------------------- | -------------------------------------------------------- | ----------- |
| Attendance rows (labor)             | `SELECT … FROM attendance_records WHERE record_date=…`   | **2026-04-10** (report − 1) |
| Temp staff (フルキャスト)           | `SELECT … FROM temp_staff WHERE record_date=…`           | 2026-04-10 (report − 1)     |
| Pack header                         | `SELECT … FROM daily_packs WHERE record_date=…`          | **2026-04-11** (= report)   |
| Pack items                          | `SELECT … FROM daily_pack_items WHERE production_date=…` | 2026-04-11 (= report)       |
| Production plan                     | `SELECT … FROM production_plan WHERE record_date=…`      | 2026-04-11 (= report)       |

### Which input file feeds which row?

| File you upload      | Filename hint    | Lands in                                            | DB date     |
| -------------------- | ---------------- | --------------------------------------------------- | ----------- |
| **Attendance PDF**   | `2026.04.10.pdf` | `attendance_records.record_date`                    | 2026-04-10  |
| **Daily-pack Excel** | `…04.11…xlsx`    | `daily_packs` / `daily_pack_items` / `production_plan` | 2026-04-11 |

So a single report consumes **two files dated one day apart** (PDF for shift 4/10 + Excel for production 4/11), and shows them together on the **2026-04-11** page.

### Note on file types

- The "Excel = report date" rule above is for **input daily-pack Excels** that you upload (`auto_uploads/daily_packs/*.xlsx`).
- The system also **generates** attendance export Excels named like `attendance_2026-04_xxx.xlsx` (referenced by `upload_batches.file_name`). Those are month-keyed, not day-keyed — they are an export of one full month of `attendance_records`, not a day file.

---

## 3. The three upload paths — they all behave the same

```
                              ┌──────────────────────────┐
   web manual upload ────────▶│                          │
   (drag-drop in UI)          │                          │
                              │  parse_pdf_data() or     │
   desktop agent ────────────▶│  daily-pack extractor    │──▶  attendance_records
   POST /api/v1/pdf/upload    │                          │     daily_packs
   POST /api/v1/xlsx/upload   │  (same code path for     │     daily_pack_items
                              │   all three sources)     │     production_plan
   auto-upload ──────────────▶│                          │
   POST /api/attendance/      │  date_service.py         │
        auto-upload           │  applies the rules       │
   POST /api/daily-packs/     │                          │
        auto-extract*         └──────────────────────────┘
```

**The date you see in the DB is determined by the file, not the upload method.** There is no special handling per source. Whichever way the file arrives:

| Upload method                     | Where it parses the date from         | Result                                                   |
| --------------------------------- | ------------------------------------- | -------------------------------------------------------- |
| **Web manual** (UI drag-drop)     | The text inside the PDF / Excel       | Same as below                                            |
| **Desktop agent** (`/api/v1/...`) | The text inside the PDF / Excel       | Same as below                                            |
| **Auto-upload** (watched folder)  | First the filename, then the contents | Same as below                                            |
| → Attendance PDF                  | →                                     | `attendance_records.record_date = PDF date`              |
| → Daily-pack Excel                | →                                     | `daily_packs.record_date = Excel date` (production date) |

If the date in the filename and the date inside the file disagree, the file contents win.

---

## 4. Quick reference — every table's date column

For an **Attendance Report 2026-04-11** (the user's running example):

| Table                       | Column            | Stores                    | Value         | Relation to report      |
| --------------------------- | ----------------- | ------------------------- | ------------- | ----------------------- |
| `attendance_records`        | `record_date`     | shift date (= PDF date)   | **2026-04-10** | report − 1             |
| `attendance_records`        | `month_year`      | shift month               | `2026-04`     | —                       |
| `temp_staff` (フルキャスト) | `record_date`     | shift date                | 2026-04-10    | report − 1              |
| `daily_packs`               | `record_date`     | production / report date  | **2026-04-11** | = report               |
| `daily_pack_items`          | `production_date` | production / report date  | 2026-04-11    | = report                |
| `production_plan`           | `record_date`     | production / report date  | 2026-04-11    | = report                |
| `upload_batches`            | `upload_date`     | wall-clock NOW()          | (timestamp)   | audit only — not a business date |
| `uploaded_file_registry`    | `target_date`     | the file's own date       | 2026-04-10 (PDF) / 2026-04-11 (Excel) | matches the file |

---

## 5. Verifying live data

For *Report 2026-04-11* — fetch both halves the way the UI would:

```bash
# Pack-side  (= report date)
PGPASSWORD=… psql -h 127.0.0.1 -U attendance -d attendance_db \
  -c "SELECT record_date, number_of_packs FROM daily_packs
      WHERE record_date='2026-04-11';"

# Attendance-side  (= report − 1)
PGPASSWORD=… psql -h 127.0.0.1 -U attendance -d attendance_db \
  -c "SELECT record_date, COUNT(*) FROM attendance_records
      WHERE record_date='2026-04-10' GROUP BY record_date;"

# Temp staff for the same shift
PGPASSWORD=… psql -h 127.0.0.1 -U attendance -d attendance_db \
  -c "SELECT record_date, SUM(total_hours) FROM temp_staff
      WHERE record_date='2026-04-10' GROUP BY record_date;"
```

---

## 6. How to change a rule

Open [`date_service.py`](date_service.py), scroll to the **`# CONFIG`** block at the top, change one constant, save. The whole app picks it up.

| Want to change…                                  | Edit…                                |
| ------------------------------------------------ | ------------------------------------ |
| PDF-to-production gap (now `+1`)                 | `PDF_TO_PRODUCTION_DAYS`             |
| Production-to-shift gap (now `-1`)               | `PRODUCTION_TO_SHIFT_DAYS`           |
| Make report a different day from production      | `REPORT_TO_PRODUCTION_DAYS`          |
| Make pack a different day from production        | `PACK_TO_PRODUCTION_DAYS`            |
| Excel epoch (almost never)                       | `EXCEL_EPOCH`                        |
| ISO / Japanese / month_year format               | `ISO_DATE` / `JP_DATE` / `ISO_MONTH` |

After editing, run:

```bash
cd /var/www/attendance_app
python3 date_service.py
```

It prints a self-check. Round-trips must all say `True`. If they don't, the constants are inconsistent.

---

## 7. Function reference (the helpers in `date_service.py`)

### Conversions — production date is the hub

| Function                    | Direction                       |
| --------------------------- | ------------------------------- |
| `pdf_to_production(d)`      | 勤怠PDF日 → 生産日              |
| `production_to_pdf(d)`      | 生産日 → 勤怠PDF日              |
| `production_to_shift(d)`    | 生産日 → シフト日               |
| `shift_to_production(d)`    | シフト日 → 生産日               |
| `report_to_production(d)`   | レポート日 → 生産日 (alias)     |
| `production_to_report(d)`   | 生産日 → レポート日 (alias)     |
| `pack_to_production(d)`     | パック日 → 生産日 (alias)       |
| `production_to_pack(d)`     | 生産日 → パック日 (alias)       |

### Convenience chains (used by API endpoints)

| Function              | Computes                          |
| --------------------- | --------------------------------- |
| `report_to_shift(d)`  | report → production → shift       |
| `report_to_pdf(d)`    | report → production → pdf         |
| `pdf_to_shift(d)`     | pdf → production → shift          |

### Table-key helpers (self-documenting names)

| Function                                   | Returns the record_date for…              |
| ------------------------------------------ | ----------------------------------------- |
| `employee_record_date(production_date)`    | `attendance_records`                      |
| `temp_staff_record_date(production_date)`  | `temp_staff` (フルキャスト / part-time)    |
| `pack_record_date(production_date)`        | `daily_packs` / `daily_pack_items`        |

### Parsing & formatting

| Function              | What it does                                    |
| --------------------- | ----------------------------------------------- |
| `parse_iso(s)`        | `'YYYY-MM-DD'` → date                           |
| `parse_flexible(s)`   | tries ISO, `YYYY/MM/DD`, `DD/MM/YYYY`, `DD-MM-YYYY` |
| `to_iso(d)`           | date → `'YYYY-MM-DD'`                           |
| `to_japanese(d)`      | date → `'YYYY年MM月DD日'`                       |
| `month_year(d)`       | date → `'YYYY-MM'` (`attendance_records.month_year`) |
| `first_of_month(s)`   | `'YYYY-MM'` → first-of-month date               |

### Ranges & windows

| Function                       | Returns                                           |
| ------------------------------ | ------------------------------------------------- |
| `date_axis(start, end)`        | inclusive ISO-string list (chart x-axis)          |
| `window(anchor, days)`         | trailing N-day `(start, end)` ending at anchor    |
| `previous_window(start, end)`  | the same-length window immediately before         |
| `add_days(d, n)`               | generic offset (e.g. cleanup cutoffs)             |

### Excel & filenames

| Function                       | What it does                                       |
| ------------------------------ | -------------------------------------------------- |
| `excel_serial_to_date(n)`      | Excel serial number → date (handles 1900 leap bug) |
| `date_from_filename(name)`     | extracts a date from a filename — handles full-width digits and 2-digit years; returns `None` if none found |

### Timestamps — audit metadata, **NOT** business dates

| Function           | Format                              | Use for…                          |
| ------------------ | ----------------------------------- | --------------------------------- |
| `now_iso()`        | `YYYY-MM-DDTHH:MM:SS` (server local)| `saved_at`, `updated_at` columns  |
| `utc_iso_z()`      | `YYYY-MM-DDTHH:MM:SSZ` (UTC)        | API responses                     |
| `filename_stamp()` | `YYYYMMDD_HHMMSS`                   | unique filenames for uploads/zips |

### Defaults

| Function       | Returns                                           |
| -------------- | ------------------------------------------------- |
| `today()`      | today (server local)                              |
| `yesterday()`  | yesterday — default report date when none given   |

---

## 8. Where rules still live in main.py (refactor TODO)

The rules below are still hard-coded in `main.py`. They will move to `date_service.py` calls in a future refactor. **If you change a rule in `date_service.py`, update these sites too** until the refactor is done.

| main.py line | What's there now                                | Should call             |
| ------------ | ------------------------------------------------ | ----------------------- |
| 4464         | `shift_date + timedelta(days=1)`                 | `shift_to_production`   |
| 5797         | `pdate - timedelta(days=1)` (temp_staff write)   | `production_to_shift`   |
| 2371         | gantt previous-day delta                         | `add_days(d, -1)`       |
| 6115         | data-status `d - timedelta(days=1)`              | `report_to_shift`       |
| 7186-7191    | mobile-summary anchor + window                   | `parse_iso` + `window`  |
| 4837-4840    | `EXCEL_EPOCH` + serial conversion                | `excel_serial_to_date`  |
| 3201         | `_extract_date_from_filename`                    | `date_from_filename`    |
| ~18 sites    | `datetime.strptime(s, "%Y-%m-%d")`               | `parse_iso`             |

---

## 9. Common pitfalls

- **Never write the offset twice.** If you see `+ timedelta(days=1)` or `- timedelta(days=1)` outside `date_service.py`, that's a bug waiting to happen — replace it with a function call.
- **Don't query `attendance_records` with a production date.** That table is keyed on shift date (= production − 1). Use `employee_record_date(production_date)`.
- **Don't use timestamps as business dates.** `now_iso()` and `utc_iso_z()` are for audit columns only. Business dates go through the conversion functions.
- **The Japanese label `フルキャスト` always means shift date.** Not production, not report.
- **Filename date vs file content date.** Auto-upload reads the filename first as a hint, but the file's internal date wins on conflict.

---

## 10. Per-project rule (locked)

Per project memory, do **not** refactor or change tap targets in the LINE send flow (`/api/line/send-mobile-link` → `/m/report` or `/m/summary`) without explicit permission. Date arithmetic feeding that endpoint is fair game; the endpoint surface is not.
