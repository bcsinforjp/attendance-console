#!/usr/bin/env python3
"""
Attendance PDF to Excel Converter - FastAPI Backend
Converts Japanese attendance PDFs to Excel files
"""

from fastapi import FastAPI, File, UploadFile, HTTPException, Query, Body, BackgroundTasks
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from calendar import monthrange
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import shutil
import threading
import time
from uuid import uuid4
import zipfile

try:
    import psutil  # type: ignore
    HAVE_PSUTIL = True
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore
    HAVE_PSUTIL = False

# Excel and PDF libraries
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
import pdfplumber
import psycopg2
from psycopg2.extras import RealDictCursor

# Create app
app = FastAPI(title="V3 Attendance Console", version="3.0")

BASE_DIR = Path(__file__).resolve().parent
EMPLOYEE_ROSTER_PATH = BASE_DIR / "employee_roster.json"
EMPLOYEE_ROSTER = json.loads(EMPLOYEE_ROSTER_PATH.read_text(encoding="utf-8"))
EMPLOYEE_ROSTER_BY_ID = {
    employee["employee_code"]: employee["name"]
    for employee in EMPLOYEE_ROSTER
}
EMPLOYEE_CODES = set(EMPLOYEE_ROSTER_BY_ID)
EXCEL_SECTION_INSERT_AFTER = "00000326"
EXCEL_SECTION_INSERT_BEFORE = "00000401"
EXCEL_SECTION_LABEL = "Section Two 2 Depanment"
SECTIONS_PATH = BASE_DIR / "sections.json"
SECTIONS = json.loads(SECTIONS_PATH.read_text(encoding="utf-8"))["sections"]
SECTION_OF_CODE = {c: s["id"] for s in SECTIONS for c in s["codes"]}
SECTION_LABEL_BY_ID = {section["id"]: section["label"] for section in SECTIONS}
SECTION_TEXT_PATTERNS = {
    1: [
        re.compile(r"製造\s*[1１一]\s*課"),
        re.compile(r"製造\s*1\s*課"),
    ],
    2: [
        re.compile(r"製造\s*[2２二]\s*課"),
        re.compile(r"製造\s*2\s*課"),
    ],
}
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)
DATABASE_HOST = os.getenv("ATTENDANCE_DB_HOST", "127.0.0.1")
DATABASE_PORT = int(os.getenv("ATTENDANCE_DB_PORT", "5432"))
DATABASE_NAME = os.getenv("ATTENDANCE_DB_NAME", "attendance_db")
DATABASE_USER = os.getenv("ATTENDANCE_DB_USER", "attendance")
DATABASE_PASSWORD = os.getenv("ATTENDANCE_DB_PASSWORD", "attendance2026")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create upload directory
UPLOAD_DIR = Path("/tmp/attendance_uploads")
EXPORT_DIR = Path("/tmp/attendance_exports")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

uploaded_files = []
parsed_data = []

def write_json_atomic(path: Path, payload: object) -> None:
    """Write JSON through a temp file so roster saves never leave half-written data."""
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temp_path, path)

def refresh_management_data(roster: list[dict], sections_payload: list[dict]) -> None:
    """Refresh global roster/section caches after management saves."""
    global EMPLOYEE_ROSTER, EMPLOYEE_ROSTER_BY_ID, EMPLOYEE_CODES
    global SECTIONS, SECTION_OF_CODE, SECTION_LABEL_BY_ID

    EMPLOYEE_ROSTER = roster
    EMPLOYEE_ROSTER_BY_ID = {
        employee["employee_code"]: employee["name"]
        for employee in EMPLOYEE_ROSTER
    }
    EMPLOYEE_CODES = set(EMPLOYEE_ROSTER_BY_ID)
    SECTIONS = sections_payload
    SECTION_OF_CODE = {code: section["id"] for section in SECTIONS for code in section["codes"]}
    SECTION_LABEL_BY_ID = {section["id"]: section["label"] for section in SECTIONS}

def management_payload_from_files() -> dict:
    """Build the management UI payload from the current roster and section maps."""
    section_lookup = {section["id"]: section["label"] for section in SECTIONS}
    employees = [
        {
            "code": employee["employee_code"],
            "name": employee["name"],
            "section_id": SECTION_OF_CODE.get(employee["employee_code"]),
            "section_label": section_lookup.get(SECTION_OF_CODE.get(employee["employee_code"])),
        }
        for employee in EMPLOYEE_ROSTER
    ]
    sections = [
        {
            "id": section["id"],
            "label": section["label"],
            "codes": list(section["codes"]),
        }
        for section in SECTIONS
    ]
    return {
        "sections": sections,
        "employees": employees,
    }

# Batch job infrastructure (multi-file upload with progress tracking).
BATCH_UPLOAD_DIR = Path("/tmp/attendance_batch_uploads")
BATCH_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
BATCH_MAX_TOTAL_BYTES = 500 * 1024 * 1024  # 500 MB hard cap per batch.
BATCH_JOB_TTL_SECONDS = 60 * 60  # 1 hour retention for completed jobs.
BATCH_CPU_THROTTLE_THRESHOLD = float(os.getenv("ATTENDANCE_BATCH_CPU_MAX", "88"))
BATCH_RAM_THROTTLE_THRESHOLD = float(os.getenv("ATTENDANCE_BATCH_RAM_MAX", "94"))
BATCH_THROTTLE_SLEEP_SECONDS = 0.75
BATCH_MAX_THROTTLE_WAITS = 12  # ~9 s of back-off per file before giving up.
BATCH_JOBS: dict[str, dict] = {}
BATCH_JOBS_LOCK = threading.Lock()

def _sample_system_load() -> dict:
    """Return current CPU/RAM usage so the batch worker can self-throttle."""
    if not HAVE_PSUTIL:
        return {"cpu_percent": None, "ram_percent": None, "ram_available_mb": None}
    try:
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        return {
            "cpu_percent": round(cpu, 1),
            "ram_percent": round(mem.percent, 1),
            "ram_available_mb": round(mem.available / (1024 * 1024), 1),
        }
    except Exception:  # pragma: no cover
        return {"cpu_percent": None, "ram_percent": None, "ram_available_mb": None}

def _batch_set(job_id: str, **updates) -> None:
    """Thread-safe shallow update of a job record."""
    with BATCH_JOBS_LOCK:
        job = BATCH_JOBS.get(job_id)
        if job is None:
            return
        job.update(updates)
        load = _sample_system_load()
        job["cpu_percent"] = load["cpu_percent"]
        job["ram_percent"] = load["ram_percent"]
        job["ram_available_mb"] = load["ram_available_mb"]

def _batch_update_file(job_id: str, index: int, **updates) -> None:
    """Thread-safe update of a single file entry inside a job."""
    with BATCH_JOBS_LOCK:
        job = BATCH_JOBS.get(job_id)
        if job is None:
            return
        files = job.get("files") or []
        if 0 <= index < len(files):
            files[index].update(updates)

def _batch_snapshot(job_id: str) -> dict | None:
    """Thread-safe read of a job record (shallow copy; safe for JSON serialization)."""
    with BATCH_JOBS_LOCK:
        job = BATCH_JOBS.get(job_id)
        if job is None:
            return None
        snapshot = {key: value for key, value in job.items() if key != "files"}
        snapshot["files"] = [dict(entry) for entry in job.get("files") or []]
        return snapshot

def _batch_cleanup_expired() -> None:
    """Drop finished jobs older than BATCH_JOB_TTL_SECONDS and remove their temp dirs."""
    cutoff = time.time() - BATCH_JOB_TTL_SECONDS
    expired: list[str] = []
    with BATCH_JOBS_LOCK:
        for job_id, job in list(BATCH_JOBS.items()):
            finished_at = job.get("finished_at_ts")
            if finished_at and finished_at < cutoff:
                expired.append(job_id)
                BATCH_JOBS.pop(job_id, None)
    for job_id in expired:
        job_dir = BATCH_UPLOAD_DIR / job_id
        if job_dir.exists():
            shutil.rmtree(job_dir, ignore_errors=True)

def _wait_for_resources(job_id: str) -> None:
    """Adaptive throttle: pause briefly when CPU/RAM are saturated."""
    if not HAVE_PSUTIL:
        return
    for _ in range(BATCH_MAX_THROTTLE_WAITS):
        load = _sample_system_load()
        cpu = load.get("cpu_percent")
        ram = load.get("ram_percent")
        if cpu is None or ram is None:
            return
        if cpu < BATCH_CPU_THROTTLE_THRESHOLD and ram < BATCH_RAM_THROTTLE_THRESHOLD:
            return
        with BATCH_JOBS_LOCK:
            job = BATCH_JOBS.get(job_id)
            if job is not None:
                job["throttled"] = True
                job["cpu_percent"] = cpu
                job["ram_percent"] = ram
        time.sleep(BATCH_THROTTLE_SLEEP_SECONDS)

EMPTY_MARKERS = {"", "__:_", "__:__", "----", "------", "早退"}
TIME_PATTERN = re.compile(r"^(?:(当|翌)\s*)?(\d{1,2}):(\d{2})$")
MONTH_PATTERN = re.compile(r"(20\d{2})[.\-/](\d{1,2})")

def get_db_connection():
    """Open a PostgreSQL connection for attendance persistence."""
    connection = psycopg2.connect(
        host=DATABASE_HOST,
        port=DATABASE_PORT,
        dbname=DATABASE_NAME,
        user=DATABASE_USER,
        password=DATABASE_PASSWORD,
    )
    return connection

def init_db() -> None:
    """Ensure the PostgreSQL tables needed for uploads and attendance rows exist."""
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS upload_batches (
                    id SERIAL PRIMARY KEY,
                    file_name VARCHAR(255) NOT NULL,
                    total_records INTEGER NOT NULL DEFAULT 0,
                    upload_date TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS attendance_records (
                    id SERIAL PRIMARY KEY,
                    upload_date TIMESTAMP NOT NULL DEFAULT NOW(),
                    file_name VARCHAR(255) NOT NULL,
                    personal_code VARCHAR(20) NOT NULL,
                    full_name VARCHAR(100) NOT NULL,
                    commute_time VARCHAR(10) DEFAULT '',
                    time_to_leave VARCHAR(10) DEFAULT '',
                    working_hours VARCHAR(10) DEFAULT '',
                    record_date DATE NOT NULL,
                    month_year VARCHAR(7) NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_attendance_code ON attendance_records(personal_code)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance_records(record_date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_attendance_month ON attendance_records(month_year)")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_packs (
                    record_date DATE PRIMARY KEY,
                    number_of_packs INTEGER NOT NULL DEFAULT 0,
                    note TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)
            # temp_staff stores フルキャスト manual entries per date. Each row is one
            # bucket of N workers starting together and leaving at the same time.
            # total_hours = headcount * hours_per_person and is used by the Summary Report
            # to fold temp-staff labor into the company-wide hour total.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS temp_staff (
                    id SERIAL PRIMARY KEY,
                    record_date DATE NOT NULL,
                    company VARCHAR(50) NOT NULL DEFAULT 'フルキャスト',
                    headcount INTEGER NOT NULL,
                    start_time VARCHAR(5) NOT NULL,
                    leave_time VARCHAR(5) NOT NULL,
                    hours_per_person NUMERIC(6,2) NOT NULL,
                    total_hours NUMERIC(8,2) NOT NULL,
                    note TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_temp_staff_date ON temp_staff(record_date)")
        connection.commit()

init_db()

def clean_cell(value: object) -> str:
    """Normalize PDF table cell values for matching and display."""
    if value is None:
        return ""
    return str(value).replace("\n", " ").strip()

def is_employee_code(value: str) -> bool:
    """Attendance rows use 8-digit employee codes; subtotal rows do not."""
    return value.isdigit() and len(value) == 8

def find_column_index(header_row: list[str], keyword: str) -> int | None:
    """Find the first header cell containing the requested keyword."""
    for index, cell in enumerate(header_row):
        if keyword in cell:
            return index
    return None

def get_row_value(row: list[str], index: int | None) -> str:
    """Safely read a column value from an extracted table row."""
    if index is None or index >= len(row):
        return ""
    return row[index]

def normalize_blank_value(value: str) -> str:
    """Convert placeholder markers to blank strings."""
    return "" if value in EMPTY_MARKERS else value

def detect_section_from_text(text: str | None) -> int | None:
    """Infer a department from PDF text when the file prints the section label."""
    if not text:
        return None
    normalized = text.replace(" ", "")
    for section_id, patterns in SECTION_TEXT_PATTERNS.items():
        for pattern in patterns:
            if pattern.search(normalized) or pattern.search(text):
                return section_id
    return None

def normalize_time_value(value: str, *, is_leave: bool = False) -> str:
    """
    Remove attendance prefixes and normalize late-night leave times.

    Leave times at or after midnight are represented in 24+ hour format,
    e.g. 1:00 AM becomes 25:00.
    """
    raw = clean_cell(value)
    if raw in EMPTY_MARKERS:
        return ""

    match = TIME_PATTERN.match(raw)
    if not match:
        return raw

    prefix, hour_str, minute_str = match.groups()
    hour = int(hour_str)
    minute = int(minute_str)

    if is_leave and (prefix == "翌" or hour <= 6):
        hour += 24

    return f"{hour}:{minute:02d}"

def time_to_minutes(value: str) -> int | None:
    """Convert a normalized H:MM string into absolute minutes."""
    normalized = normalize_blank_value(clean_cell(value))
    if not normalized:
        return None

    match = re.match(r"^(\d{1,2}):(\d{2})$", normalized)
    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2))
    return hour * 60 + minute

def calculate_working_hours(start_time: str, leave_time: str) -> str:
    """Calculate one working-hours value like 8:00 hr from start/end times."""
    start_minutes = time_to_minutes(start_time)
    leave_minutes = time_to_minutes(leave_time)
    if start_minutes is None or leave_minutes is None or leave_minutes < start_minutes:
        return ""

    diff_minutes = leave_minutes - start_minutes
    hours = diff_minutes // 60
    minutes = diff_minutes % 60
    return f"{hours}:{minutes:02d} hr"

def calculate_temp_staff_hours(start_time: str, leave_time: str) -> float:
    """
    Hours for one フルキャスト row. Handles overnight leave times: if the leave hour
    is <= 6, it's treated as the following morning (e.g. start 19:00 leave 1:30 = 6.5h).
    Returns 0.0 if inputs are unparseable.
    """
    raw_start = (start_time or "").strip()
    raw_leave = (leave_time or "").strip()
    match_start = re.match(r"^(\d{1,2}):(\d{2})$", raw_start)
    match_leave = re.match(r"^(\d{1,2}):(\d{2})$", raw_leave)
    if not match_start or not match_leave:
        return 0.0
    start_h = int(match_start.group(1))
    start_m = int(match_start.group(2))
    leave_h = int(match_leave.group(1))
    leave_m = int(match_leave.group(2))
    if leave_h <= 6:
        leave_h += 24
    start_total = start_h * 60 + start_m
    leave_total = leave_h * 60 + leave_m
    if leave_total <= start_total:
        return 0.0
    return round((leave_total - start_total) / 60, 2)

def parse_working_hours_minutes(value: str) -> int | None:
    """Convert values like 8:01 hr into minutes for dashboard calculations."""
    normalized = normalize_blank_value(clean_cell(value)).replace(" hr", "")
    if not normalized:
        return None

    match = re.match(r"^(\d+):(\d{2})$", normalized)
    if not match:
        return None

    return int(match.group(1)) * 60 + int(match.group(2))

def format_average_hours(minutes_values: list[int]) -> float:
    """Return an hours float rounded to 2 decimals for API summaries."""
    if not minutes_values:
        return 0.0
    return round((sum(minutes_values) / len(minutes_values)) / 60, 2)

def record_has_data(record: dict[str, str]) -> bool:
    """Check whether a roster row contains at least one non-blank value."""
    return any(record.get(field) for field in ("commute_time", "leave_time", "working_hours"))

def count_records_with_data(records: list[dict[str, str]]) -> int:
    """Count output rows that contain actual attendance data."""
    return sum(1 for record in records if record_has_data(record))

def extract_month_year(filename: str) -> str:
    """Derive a YYYY-MM value from the uploaded filename when available."""
    match = MONTH_PATTERN.search(filename)
    if not match:
        return datetime.now().strftime("%Y-%m")

    year, month = match.groups()
    return f"{year}-{int(month):02d}"

def resolve_month(month: str | None = None) -> str:
    """Choose the requested month or fall back to the latest saved batch."""
    if month:
        return month

    with get_db_connection() as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT month_year
                FROM attendance_records
                ORDER BY upload_date DESC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
    return row["month_year"] if row else datetime.now().strftime("%Y-%m")

def parse_requested_codes(raw_values: list[str] | None) -> list[str]:
    """Split repeated or comma/newline separated code inputs into clean values."""
    if not raw_values:
        return []

    codes: list[str] = []
    for raw in raw_values:
        if raw is None:
            continue
        for code in re.split(r"[\s,]+", raw.strip()):
            if code:
                codes.append(code)
    return codes

def create_export_filename(original_name: str) -> str:
    """Build a safe Excel filename for an uploaded PDF."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(original_name).stem).strip("._")
    if not safe_stem:
        safe_stem = "attendance"
    return f"{safe_stem}_{timestamp}_{uuid4().hex[:8]}.xlsx"

def create_bundle_filename() -> str:
    """Build a zip filename for multi-file conversion."""
    return f"attendance_bundle_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}.zip"

def extract_pdf_metadata(file_path: Path) -> dict[str, object]:
    """Pull production date and pack count from the PDF text content.

    Dates are looked up in this order (first hit wins):
      1. 処理日：YYYY/MM/DD   — the attendance working-day / processing-day line
      2. YYYY年MM月DD日         — generic Japanese long-form date
    """
    metadata: dict[str, object] = {"record_date": None, "number_of_packs": None}
    try:
        with pdfplumber.open(file_path) as pdf:
            full_text = "\n".join((page.extract_text() or "") for page in pdf.pages)
    except Exception:
        return metadata

    # 1) Prefer 処理日 (fullwidth or ASCII colon, slash separators)
    proc_match = re.search(
        r"処理日\s*[:：]\s*(\d{4})\s*[/／年\-\.]\s*(\d{1,2})\s*[/／月\-\.]\s*(\d{1,2})",
        full_text,
    )
    if proc_match:
        try:
            year, month, day = (int(part) for part in proc_match.groups())
            metadata["record_date"] = datetime(year, month, day).date()
        except ValueError:
            pass

    # 2) Fallback to generic Japanese long-form date
    if metadata["record_date"] is None:
        date_match = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", full_text)
        if date_match:
            try:
                year, month, day = (int(part) for part in date_match.groups())
                metadata["record_date"] = datetime(year, month, day).date()
            except ValueError:
                pass

    # Anchor to the 製造パック数 label so productivity numbers like 29.1P/h are ignored.
    pack_match = re.search(r"製造パック数[^\d]*([\d,]+)\s*[PＰ]", full_text)
    if pack_match:
        try:
            metadata["number_of_packs"] = int(pack_match.group(1).replace(",", ""))
        except ValueError:
            pass

    return metadata

def find_attendance_mismatches(
    record_date,
    records: list[dict[str, str]],
) -> list[dict[str, object]]:
    """Compare freshly parsed PDF records with whatever the DB already holds for that date."""
    if record_date is None:
        return []

    with get_db_connection() as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT personal_code, full_name, commute_time, time_to_leave, working_hours
                FROM attendance_records
                WHERE record_date = %s
                """,
                (record_date,),
            )
            existing_by_code = {row["personal_code"]: row for row in cursor.fetchall()}

    mismatches: list[dict[str, object]] = []
    for record in records:
        if not record_has_data(record):
            continue
        code = record["employee_code"]
        prior = existing_by_code.get(code)
        if prior is None:
            continue
        diffs: dict[str, dict[str, str]] = {}
        if (prior["commute_time"] or "") != (record.get("commute_time") or ""):
            diffs["commute_time"] = {
                "db": prior["commute_time"] or "",
                "pdf": record.get("commute_time", ""),
            }
        if (prior["time_to_leave"] or "") != (record.get("leave_time") or ""):
            diffs["leave_time"] = {
                "db": prior["time_to_leave"] or "",
                "pdf": record.get("leave_time", ""),
            }
        if (prior["working_hours"] or "") != (record.get("working_hours") or ""):
            diffs["working_hours"] = {
                "db": prior["working_hours"] or "",
                "pdf": record.get("working_hours", ""),
            }
        if diffs:
            mismatches.append({
                "employee_code": code,
                "name": record.get("name", "") or prior["full_name"],
                "differences": diffs,
            })
    return mismatches

def upsert_pack_count_for_date(record_date, pack_count: int, source: str | None = None) -> None:
    """Save the pack count extracted from a PDF for a given production date."""
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO daily_packs (record_date, number_of_packs, note)
                VALUES (%s, %s, %s)
                ON CONFLICT (record_date) DO UPDATE
                    SET number_of_packs = EXCLUDED.number_of_packs,
                        note = COALESCE(EXCLUDED.note, daily_packs.note),
                        updated_at = NOW()
                """,
                (record_date, pack_count, f"auto from {source}" if source else None),
            )
        connection.commit()

def save_batch_to_db(
    source_filename: str,
    export_filename: str,
    records: list[dict[str, str]],
    converted_at: str,
    record_date=None,
) -> tuple[int, int]:
    """Persist one converted upload batch and its attendance rows."""
    month_year = extract_month_year(source_filename)
    records_processed = count_records_with_data(records)
    if record_date is None:
        record_date = datetime.strptime(f"{month_year}-01", "%Y-%m-%d").date()

    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM attendance_records
                WHERE file_name = %s AND month_year = %s
                """,
                (source_filename, month_year),
            )
            cursor.execute(
                """
                DELETE FROM upload_batches
                WHERE file_name = %s
                """,
                (export_filename,),
            )
            cursor.execute(
                """
                INSERT INTO upload_batches (file_name, total_records, upload_date)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (export_filename, records_processed, converted_at),
            )
            batch_id = cursor.fetchone()[0]
            cursor.executemany(
                """
                INSERT INTO attendance_records (
                    upload_date,
                    file_name,
                    personal_code,
                    full_name,
                    commute_time,
                    time_to_leave,
                    working_hours,
                    record_date,
                    month_year,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        converted_at,
                        source_filename,
                        record["employee_code"],
                        record["name"],
                        record.get("commute_time", ""),
                        record.get("leave_time", ""),
                        record.get("working_hours", ""),
                        record_date,
                        month_year,
                        converted_at,
                    )
                    for record in records
                ],
            )
        connection.commit()

    return batch_id, records_processed

def list_attendance_rows(month: str):
    """Fetch saved attendance rows for a given month."""
    with get_db_connection() as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT personal_code AS employee_code,
                       full_name,
                       commute_time,
                       time_to_leave AS leave_time,
                       working_hours,
                       CASE
                           WHEN commute_time <> '' OR time_to_leave <> '' OR working_hours <> '' THEN 1
                           ELSE 0
                       END AS has_data,
                       upload_date AS converted_at,
                       file_name AS source_filename,
                       record_date
                FROM attendance_records
                WHERE month_year = %s
                ORDER BY personal_code, upload_date
                """,
                (month,),
            )
            return cursor.fetchall()

def build_preview_payload(
    filename: str,
    file_size: int,
    records: list[dict[str, str]],
    *,
    file_count: int = 1,
    preview_filename: str | None = None,
) -> dict[str, object]:
    """Create a consistent preview payload for one or many files."""
    return {
        "filename": filename,
        "preview_filename": preview_filename or filename,
        "file_size": file_size,
        "file_count": file_count,
        "status": "success",
        # Return the full aligned roster so the frontend can paginate/filter locally.
        "records": records,
        "total_records": len(records),
        "records_with_data": count_records_with_data(records),
        "extracted_at": datetime.now().isoformat(),
    }

async def parse_uploaded_pdf(
    file: UploadFile,
) -> tuple[str, int, list[dict[str, str]], dict[str, object]]:
    """Save, parse, and roster-align an uploaded PDF, returning metadata too."""
    original_name, file_path, content = await save_uploaded_pdf(file)
    records = apply_employee_roster(parse_pdf_data(file_path))
    metadata = extract_pdf_metadata(file_path)
    return original_name, len(content), records, metadata

def export_records_to_excel(
    source_filename: str,
    records: list[dict[str, str]],
    record_date=None,
) -> tuple[str, Path, int, int]:
    """Create one Excel file from roster-aligned records and save it to the DB."""
    excel_filename = create_export_filename(source_filename)
    excel_path = EXPORT_DIR / excel_filename
    create_excel_file(records, excel_path)

    converted_at = datetime.now().isoformat()
    batch_id, records_processed = save_batch_to_db(
        source_filename,
        excel_filename,
        records,
        converted_at,
        record_date=record_date,
    )

    uploaded_files.append({
        "source_filename": source_filename,
        "export_filename": excel_filename,
        "records_processed": records_processed,
        "converted_at": converted_at,
        "batch_id": batch_id,
    })

    return excel_filename, excel_path, records_processed, batch_id

def apply_employee_roster(records: list[dict[str, str]]) -> list[dict[str, str]]:
    """Return rows in the exact master roster order, with blanks for missing data."""
    records_by_id = {
        record["employee_code"]: record
        for record in records
        if record["employee_code"] in EMPLOYEE_ROSTER_BY_ID
    }

    rostered_records = []
    for employee in EMPLOYEE_ROSTER:
        code = employee["employee_code"]
        parsed_record = records_by_id.get(code, {})
        rostered_records.append({
            "employee_code": code,
            "name": employee["name"],
            "commute_time": parsed_record.get("commute_time", ""),
            "leave_time": parsed_record.get("leave_time", ""),
            "working_hours": parsed_record.get("working_hours", ""),
        })

    return rostered_records

def build_record_from_row(
    row: list[str],
    columns: dict[str, int | None],
    *,
    section_id: int | None = None,
) -> dict[str, str] | None:
    """Convert one extracted PDF row into the API's record shape."""
    code = get_row_value(row, columns["employee_code"])
    if not is_employee_code(code):
        return None

    commute_time = normalize_time_value(get_row_value(row, columns["commute_time"]))
    leave_time = normalize_time_value(get_row_value(row, columns["leave_time"]), is_leave=True)

    return {
        "employee_code": code,
        "name": get_row_value(row, columns["name"]),
        "commute_time": commute_time,
        "leave_time": leave_time,
        "working_hours": calculate_working_hours(commute_time, leave_time),
        "section_id": section_id,
        "section_label": SECTION_LABEL_BY_ID.get(section_id, "未配属"),
    }

def parse_pdf_data(file_path: Path) -> list[dict[str, str]]:
    """Parse attendance PDF and extract data"""
    try:
        records = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                page_section_id = detect_section_from_text(page_text)
                tables = page.extract_tables()
                if tables:
                    for table in tables:
                        normalized_rows = [[clean_cell(cell) for cell in row] for row in table if row]
                        header_row = next((row for row in normalized_rows if any("個人" in cell for cell in row)), None)
                        if not header_row:
                            continue

                        columns = {
                            "employee_code": find_column_index(header_row, "個人"),
                            "name": find_column_index(header_row, "氏名"),
                            "commute_time": find_column_index(header_row, "出勤時刻"),
                            "leave_time": find_column_index(header_row, "退勤時刻"),
                        }

                        for row in normalized_rows:
                            record = build_record_from_row(row, columns, section_id=page_section_id)
                            if record:
                                records.append(record)

        if not records:
            raise ValueError("No attendance records were found in the PDF.")

        return records
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Unable to extract attendance data from the PDF: {exc}") from exc

def validate_pdf_content(content: bytes) -> None:
    """Reject empty uploads and obvious non-PDF files before parsing."""
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if b"%PDF" not in content[:1024]:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid PDF.")

async def save_uploaded_pdf(file: UploadFile) -> tuple[str, Path, bytes]:
    """Persist the uploaded PDF using a safe, unique filename."""
    original_name = Path(file.filename or "").name
    if not original_name:
        raise HTTPException(status_code=400, detail="Uploaded file must include a filename.")

    if Path(original_name).suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    content = await file.read()
    validate_pdf_content(content)

    stored_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex}.pdf"
    file_path = UPLOAD_DIR / stored_name
    file_path.write_bytes(content)

    return original_name, file_path, content

def build_download_url(filename: str) -> str:
    """Return an app-local API path; the proxy prefix is added by the frontend."""
    return f"/api/download/{filename}"

def get_export_file_path(filename: str) -> Path:
    """Resolve a requested export filename inside the export directory only."""
    safe_name = Path(filename).name
    if safe_name != filename or Path(safe_name).suffix.lower() not in {".xlsx", ".zip"}:
        raise HTTPException(status_code=400, detail="Invalid filename.")

    file_path = (EXPORT_DIR / safe_name).resolve()
    if file_path.parent != EXPORT_DIR.resolve():
        raise HTTPException(status_code=400, detail="Invalid filename.")

    return file_path

def create_excel_file(records: list[dict[str, str]], filename: Path) -> Path:
    """Create readable Excel file with Japanese headers"""
    wb = Workbook()
    ws = wb.active
    ws.title = "勤務表"
    
    # Define styles
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_font = Font(name='MS ゴシック', size=11, bold=True, color="FFFFFF")
    data_font = Font(name='MS ゴシック', size=10)
    section_fill = PatternFill(start_color="D9EAF7", end_color="D9EAF7", fill_type="solid")
    section_font = Font(name='MS ゴシック', size=10, bold=True)
    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    center_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
    
    # Add title
    ws['A1'] = f"勤務表　{datetime.now().strftime('%Y年%m月%d日')}"
    ws['A1'].font = Font(name='MS ゴシック', size=14, bold=True)
    ws.merge_cells('A1:E1')
    ws['A1'].alignment = center_align
    ws.row_dimensions[1].height = 25
    
    # Add headers
    headers = ['個人コード', '氏名', '出勤時間', '退勤時間', '労働時間']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=3, column=col)
        cell.value = header
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align
        cell.border = border
    
    ws.row_dimensions[3].height = 20
    
    # Add data rows
    excel_rows: list[dict[str, str] | None] = []
    for index, record in enumerate(records):
        excel_rows.append(record)
        if (
            record.get("employee_code") == EXCEL_SECTION_INSERT_AFTER
            and index + 1 < len(records)
            and records[index + 1].get("employee_code") == EXCEL_SECTION_INSERT_BEFORE
        ):
            excel_rows.append(None)

    current_row = 4
    for record in excel_rows:
        if record is None:
            ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=5)
            section_cell = ws.cell(row=current_row, column=1)
            section_cell.value = EXCEL_SECTION_LABEL
            section_cell.font = section_font
            section_cell.fill = section_fill
            section_cell.alignment = center_align
            section_cell.border = border
            for col in range(2, 6):
                ws.cell(row=current_row, column=col).border = border
                ws.cell(row=current_row, column=col).fill = section_fill
            ws.row_dimensions[current_row].height = 20
            current_row += 1
            continue

        ws.cell(row=current_row, column=1).value = record.get('employee_code', '')
        ws.cell(row=current_row, column=2).value = record.get('name', '')
        ws.cell(row=current_row, column=3).value = record.get('commute_time', '')
        ws.cell(row=current_row, column=4).value = record.get('leave_time', '')
        ws.cell(row=current_row, column=5).value = record.get('working_hours', '')

        for col in range(1, 6):
            cell = ws.cell(row=current_row, column=col)
            cell.font = data_font
            cell.alignment = center_align
            cell.border = border

        ws.row_dimensions[current_row].height = 18
        current_row += 1
    
    # Set column widths
    ws.column_dimensions['A'].width = 12
    ws.column_dimensions['B'].width = 15
    ws.column_dimensions['C'].width = 12
    ws.column_dimensions['D'].width = 12
    ws.column_dimensions['E'].width = 14
    
    # Add summary row
    summary_row = current_row + 1
    ws.cell(row=summary_row, column=1).value = "合計"
    ws.cell(row=summary_row, column=1).font = Font(name='MS ゴシック', size=10, bold=True)
    ws.cell(row=summary_row, column=2).value = f"従業員数: {len(records)}"
    ws.cell(row=summary_row, column=2).font = Font(name='MS ゴシック', size=10, bold=True)
    
    # Save file
    wb.save(filename)
    return filename

@app.get("/")
async def root():
    """Serve web interface"""
    return FileResponse(BASE_DIR / "index.html")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/gantt")
async def gantt_page():
    """Standalone attendance Gantt chart (A4 portrait, printable).

    `no-store` header ensures the browser never serves a stale template after a
    redesign, so *every* date sees the newest layout on reload.
    """
    return FileResponse(
        STATIC_DIR / "gantt.html",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )

@app.get("/console")
async def console_page():
    """V3 Attendance Console — four-tab entry workflow."""
    return FileResponse(
        STATIC_DIR / "console.html",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )

@app.get("/management")
async def management_page():
    """Mockup user-management GUI for roster reassignment approval."""
    return FileResponse(
        STATIC_DIR / "management.html",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )

@app.get("/api/management/bootstrap")
async def management_bootstrap():
    """Return roster and section metadata for the management UI."""
    return management_payload_from_files()

@app.put("/api/management/roster")
async def management_save_roster(payload: dict = Body(...)):
    """Persist the management board into employee_roster.json and sections.json."""
    raw_employees = payload.get("employees")
    if not isinstance(raw_employees, list):
        raise HTTPException(status_code=400, detail="employees must be a list.")

    section_by_id = {int(section["id"]): section for section in SECTIONS}
    next_codes_by_section = {section_id: [] for section_id in section_by_id}
    next_roster: list[dict[str, str]] = []
    seen_codes: set[str] = set()

    for index, raw_employee in enumerate(raw_employees, start=1):
        if not isinstance(raw_employee, dict):
            raise HTTPException(status_code=400, detail=f"Employee row {index} is invalid.")

        code = str(raw_employee.get("code") or raw_employee.get("employee_code") or "").strip()
        name = str(raw_employee.get("name") or "").strip()
        try:
            section_id = int(raw_employee.get("section_id"))
        except (TypeError, ValueError):
            section_id = 0

        if not is_employee_code(code):
            raise HTTPException(status_code=400, detail=f"Employee row {index} has an invalid code.")
        if not name:
            raise HTTPException(status_code=400, detail=f"Employee {code} is missing a name.")
        if code in seen_codes:
            raise HTTPException(status_code=400, detail=f"Employee code {code} is duplicated.")
        if section_id not in section_by_id:
            raise HTTPException(status_code=400, detail=f"Employee {code} has an invalid section.")

        seen_codes.add(code)
        next_roster.append({"employee_code": code, "name": name})
        next_codes_by_section[section_id].append(code)

    next_sections = [
        {
            "id": int(section["id"]),
            "label": section["label"],
            "codes": next_codes_by_section[int(section["id"])],
        }
        for section in SECTIONS
    ]

    try:
        write_json_atomic(EMPLOYEE_ROSTER_PATH, next_roster)
        write_json_atomic(SECTIONS_PATH, {"sections": next_sections})
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Unable to save roster files: {exc}") from exc

    refresh_management_data(next_roster, next_sections)
    response = management_payload_from_files()
    response["saved_at"] = datetime.now().isoformat()
    return response

@app.post("/api/management/import-pdf")
async def management_import_pdf(file: UploadFile = File(...)):
    """Parse an attendance PDF and return raw employee rows for import selection."""
    original_name, file_path, _content = await save_uploaded_pdf(file)
    try:
        raw_records = parse_pdf_data(file_path)
    except ValueError as exc:
        return {
            "filename": original_name,
            "record_count": 0,
            "rows": [],
            "message": str(exc),
        }
    seen_codes: set[str] = set()
    rows: list[dict[str, str]] = []
    section_lookup = {section["id"]: section["label"] for section in SECTIONS}

    for record in raw_records:
        code = (record.get("employee_code") or "").strip()
        name = (record.get("name") or "").strip()
        if not is_employee_code(code) or not name or code in seen_codes:
            continue
        seen_codes.add(code)
        section_id = record.get("section_id") or SECTION_OF_CODE.get(code)
        try:
            section_id = int(section_id) if section_id is not None else None
        except (TypeError, ValueError):
            section_id = None
        rows.append({
            "employee_code": code,
            "name": name,
            "section_id": section_id,
            "section_label": record.get("section_label") or section_lookup.get(section_id, "未配属"),
        })

    return {
        "filename": original_name,
        "record_count": len(rows),
        "rows": rows,
    }

@app.get("/summary")
async def summary_page():
    """Attendance Summary dashboard — productivity KPIs with target lines,
    day/week/month range selector, and period-over-period comparisons.
    Targets: Section1=85 P/h, Section2=35 P/h, Combined=25 P/h.
    """
    return FileResponse(
        STATIC_DIR / "summary.html",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )

@app.get("/api/gantt/latest-date")
async def gantt_latest_date():
    """Most recent record_date in the DB, for default picker value."""
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT MAX(record_date) FROM attendance_records")
            row = cursor.fetchone()
            latest = row[0].isoformat() if row and row[0] else None
    return {"date": latest}

@app.get("/api/gantt/dates-with-data")
async def gantt_dates_with_data():
    """Dates that have at least one non-empty attendance row (most recent first)."""
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT record_date
                FROM attendance_records
                WHERE commute_time <> '' OR time_to_leave <> '' OR working_hours <> ''
                ORDER BY record_date DESC
                LIMIT 30
                """
            )
            dates = [r[0].isoformat() for r in cursor.fetchall() if r[0]]
    return {"dates": dates}

def _gantt_clean_wh(value: str | None) -> str:
    """Normalize working_hours to plain H:MM (strip trailing 'hr'/'h')."""
    s = (value or "").strip()
    s = re.sub(r"\s*hrs?\.?\s*$", "", s, flags=re.IGNORECASE).strip()
    return s or "0:00"


def _gantt_wh_to_hours(clean_wh: str) -> float:
    if not clean_wh or clean_wh == "0:00":
        return 0.0
    try:
        h_str, m_str = clean_wh.split(":")
        return int(h_str) + int(m_str) / 60
    except (ValueError, AttributeError):
        return 0.0


def _gantt_hours_to_hhmm(hours: float) -> str:
    if hours <= 0:
        return "0:00"
    total_minutes = round(hours * 60)
    h, m = divmod(total_minutes, 60)
    return f"{h}:{m:02d}"


def _gantt_compute_for_date(cursor, record_date: str, roster_index: dict) -> tuple[list[dict], dict]:
    """Pull attendance + packs for one date, bucket by section, compute productivity.

    Pure function of the cursor — reusable for current date and previous day,
    so both appear in the API response and the frontend can draw up/down deltas
    without a second round-trip.
    """
    cursor.execute(
        """
        SELECT DISTINCT ON (personal_code)
               personal_code AS code,
               full_name AS name,
               commute_time,
               time_to_leave,
               working_hours
        FROM attendance_records
        WHERE record_date = %s
        ORDER BY personal_code, upload_date DESC
        """,
        (record_date,),
    )
    rows = cursor.fetchall()
    cursor.execute(
        "SELECT number_of_packs FROM daily_packs WHERE record_date = %s",
        (record_date,),
    )
    pack_row = cursor.fetchone()

    # Fetch フルキャスト / temp-staff entries for this date so they can be
    # shown as synthetic rows at the END of 製造２課 and folded into Section 2's
    # productivity totals (hours + headcount). Each saved temp_staff row
    # becomes one synthetic gantt row — the group worked one shift together.
    cursor.execute(
        """
        SELECT id, company, headcount, start_time, leave_time,
               hours_per_person, total_hours, note
        FROM temp_staff
        WHERE record_date = %s
        ORDER BY start_time, id
        """,
        (record_date,),
    )
    temp_rows = cursor.fetchall() or []

    buckets: dict[int, list[dict]] = {s["id"]: [] for s in SECTIONS}
    buckets[0] = []  # Unassigned
    for r in rows:
        sid = SECTION_OF_CODE.get(r["code"], 0)
        buckets[sid].append({
            "code": r["code"],
            "name": r["name"] or "",
            "in": (r["commute_time"] or "").strip() or None,
            "out": (r["time_to_leave"] or "").strip() or None,
            "wh": _gantt_clean_wh(r["working_hours"]),
            "is_temp": False,
        })

    # Sort each bucket by roster index (authoritative order from employee_roster.json)
    # BEFORE appending temp-staff rows so they stay pinned at the end.
    for sid in buckets:
        buckets[sid].sort(
            key=lambda row: (roster_index.get(row["code"], 10**9), row["code"])
        )

    # Append temp_staff as synthetic rows at the end of Section 2 (製造２課).
    # Each row carries its group metadata (headcount, total_hours) so the
    # productivity math downstream can fold the group into Section 2 totals
    # without double-counting.
    temp_staff_total_hours = 0.0
    temp_staff_headcount = 0
    for t in temp_rows:
        headcount = int(t["headcount"] or 0)
        if headcount <= 0:
            continue
        hours_per_person = float(t["hours_per_person"] or 0)
        group_total_hours = float(t["total_hours"] or (hours_per_person * headcount))
        company = (t["company"] or "フルキャスト").strip() or "フルキャスト"
        synthetic = {
            "code": f"TEMP-{t['id']}",
            "name": f"{company} × {headcount}名",
            "in": (t["start_time"] or None),
            "out": (t["leave_time"] or None),
            # wh is per-person so the gantt bar length matches one person's shift
            # (the whole group shares identical start/leave).
            "wh": _gantt_hours_to_hhmm(hours_per_person),
            "is_temp": True,
            "headcount": headcount,
            "total_hours": round(group_total_hours, 4),
        }
        buckets[2].append(synthetic)
        temp_staff_total_hours += group_total_hours
        temp_staff_headcount += headcount

    sections_out = [
        {"id": s["id"], "label": s["label"], "rows": buckets[s["id"]]}
        for s in SECTIONS
    ]
    if buckets[0]:
        sections_out.append({"id": 0, "label": "Unassigned", "rows": buckets[0]})

    total_packs = 0
    if pack_row and pack_row.get("number_of_packs") is not None:
        try:
            total_packs = int(pack_row["number_of_packs"])
        except (TypeError, ValueError):
            total_packs = 0

    prod_sections: list[dict] = []
    combined_hours = 0.0
    combined_present = 0
    for s in SECTIONS:
        sect_rows = buckets[s["id"]]
        # For temp-staff rows we use the group total_hours (= headcount × hours);
        # for regular rows we parse "H:MM" working_hours to a decimal.
        sect_hours = sum(
            (float(r["total_hours"]) if r.get("is_temp") else _gantt_wh_to_hours(r["wh"]))
            for r in sect_rows
        )
        # staff_present counts: temp rows contribute their full headcount;
        # regular rows count as 1 if they actually clocked in.
        sect_present = sum(
            (int(r.get("headcount") or 0) if r.get("is_temp")
             else (1 if _gantt_wh_to_hours(r["wh"]) > 0 else 0))
            for r in sect_rows
        )
        # staff_total: temp rows also contribute headcount (a 5-person
        # フルキャスト group is 5 slots), regular rows contribute 1 each.
        sect_total = sum(
            (int(r.get("headcount") or 0) if r.get("is_temp") else 1)
            for r in sect_rows
        )
        sect_lp = (total_packs / sect_hours) if sect_hours > 0 else 0.0
        prod_sections.append({
            "id": s["id"],
            "label": s["label"],
            "staff_present": sect_present,
            "staff_total": sect_total,
            "total_hours": round(sect_hours, 4),
            "total_hours_hhmm": _gantt_hours_to_hhmm(sect_hours),
            "lp": round(sect_lp, 2),
        })
        combined_hours += sect_hours
        combined_present += sect_present

    lp_combined = (total_packs / combined_hours) if combined_hours > 0 else 0.0
    productivity = {
        "date": record_date,
        "total_packs": total_packs,
        "sections": prod_sections,
        "combined": {
            "staff_present": combined_present,
            "total_hours": round(combined_hours, 4),
            "total_hours_hhmm": _gantt_hours_to_hhmm(combined_hours),
            "lp": round(lp_combined, 2),
        },
        # Separate visibility into temp-staff contribution so the UI can show
        # "includes X フルキャスト hours" without re-summing the data.
        "temp_staff": {
            "headcount": temp_staff_headcount,
            "total_hours": round(temp_staff_total_hours, 4),
            "total_hours_hhmm": _gantt_hours_to_hhmm(temp_staff_total_hours),
            "row_count": len(temp_rows),
        },
    }
    return sections_out, productivity


@app.get("/api/gantt/{record_date}")
async def gantt_for_date(record_date: str):
    """Attendance rows for one date, grouped by section, with productivity summary
    and a *previous-day* productivity block so the frontend can draw delta arrows.

    Row order within each section is driven by the order of entries in
    employee_roster.json (single source of truth). When the JSON is updated and
    the service is restarted, every downstream output — Gantt display, reports,
    Excel exports — reflects the new ordering automatically.
    """
    try:
        current_dt = datetime.strptime(record_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="record_date must be YYYY-MM-DD")
    prev_date_str = (current_dt - timedelta(days=1)).isoformat()

    roster_index = {
        employee["employee_code"]: idx
        for idx, employee in enumerate(EMPLOYEE_ROSTER)
    }

    with get_db_connection() as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            sections_out, productivity = _gantt_compute_for_date(
                cursor, record_date, roster_index
            )
            _, prev_productivity = _gantt_compute_for_date(
                cursor, prev_date_str, roster_index
            )

    productivity["previous_date"] = prev_date_str
    productivity["previous"] = {
        "total_packs": prev_productivity["total_packs"],
        "sections": prev_productivity["sections"],
        "combined": prev_productivity["combined"],
    }

    return {
        "date": record_date,
        "sections": sections_out,
        "productivity": productivity,
    }

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM upload_batches")
            batch_count = cursor.fetchone()[0]
    return {
        "status": "healthy",
        "version": "2.0",
        "storage": "postgresql",
        "database": "postgresql",
        "saved_batches": batch_count,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/roster/codes", response_class=PlainTextResponse)
async def roster_codes_text(code: list[str] | None = Query(default=None)):
    """
    Return only the requested employee codes as plain text, one code per line.
    Example: /api/roster/codes?code=00000326&code=00000401
    """
    requested_codes = parse_requested_codes(code)
    matched_codes = [employee_code for employee_code in requested_codes if employee_code in EMPLOYEE_CODES]
    return "\n".join(matched_codes)

@app.post("/api/preview")
async def preview_pdf(file: UploadFile = File(...)):
    """
    Upload PDF and preview extracted data
    """
    try:
        original_name, file_size, records, metadata = await parse_uploaded_pdf(file)
        preview_data = build_preview_payload(original_name, file_size, records)
        record_date = metadata.get("record_date")
        preview_data["record_date"] = record_date.isoformat() if record_date else None
        preview_data["number_of_packs"] = metadata.get("number_of_packs")

        parsed_data.append(preview_data)
        return preview_data
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected error while previewing PDF: {exc}") from exc

@app.post("/api/preview-multiple")
async def preview_multiple_pdfs(files: list[UploadFile] = File(...)):
    """Preview a multi-file upload by showing the first file and total counts."""
    if not files:
        raise HTTPException(status_code=400, detail="Please upload at least one PDF file.")

    try:
        parsed_files = [await parse_uploaded_pdf(file) for file in files]
        preview_name, preview_size, preview_records, preview_metadata = parsed_files[0]
        total_records = sum(len(records) for _, _, records, _ in parsed_files)
        records_with_data = sum(count_records_with_data(records) for _, _, records, _ in parsed_files)

        preview_data = build_preview_payload(
            preview_name,
            preview_size,
            preview_records,
            file_count=len(parsed_files),
            preview_filename=preview_name,
        )
        preview_data["total_records"] = total_records
        preview_data["records_with_data"] = records_with_data
        preview_record_date = preview_metadata.get("record_date")
        preview_data["record_date"] = preview_record_date.isoformat() if preview_record_date else None
        preview_data["number_of_packs"] = preview_metadata.get("number_of_packs")
        preview_data["files"] = [
            {
                "filename": filename,
                "total_records": len(records),
                "records_with_data": count_records_with_data(records),
                "record_date": metadata.get("record_date").isoformat() if metadata.get("record_date") else None,
                "number_of_packs": metadata.get("number_of_packs"),
            }
            for filename, _file_size, records, metadata in parsed_files
        ]

        parsed_data.append(preview_data)
        return preview_data
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected error while previewing PDFs: {exc}") from exc

# ==============================================================
# Auto-upload: watched folder → latest PDF → preview (and optional save)
# ==============================================================
# Hardcoded source. On Windows the user's folder is:
#     C:\Users\Buddhika\Desktop\人時生産性　PDF
# On the Raspberry Pi running this service, that folder must be reachable
# from the filesystem — either via a CIFS/Samba mount of the Windows share
# or by rsyncing the PDFs to a local path. Override via env var
# ATTENDANCE_AUTO_UPLOAD_DIR if needed.
AUTO_UPLOAD_DIR = Path(
    os.environ.get(
        "ATTENDANCE_AUTO_UPLOAD_DIR",
        "/mnt/windows_share/Buddhika/Desktop/人時生産性　PDF",
    )
)
# Log on import so systemd journal shows the route was registered and where it looks.
print(f"[AUTO_UPLOAD] watched folder = {AUTO_UPLOAD_DIR} (exists={AUTO_UPLOAD_DIR.exists()})")

def _pick_latest_pdf_in(folder: Path) -> Path | None:
    """Pick the newest attendance PDF in the watched folder.

    Filenames embed the date as the last date-like token; sorting the
    filenames descending gives us the latest automatically. As a tie-
    breaker we fall back to mtime.
    """
    if not folder.exists() or not folder.is_dir():
        return None
    pdfs = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"]
    if not pdfs:
        return None
    # Sort by filename (descending) — dates are embedded in the name.
    # Secondary sort by mtime so same-prefix names still pick the newest.
    pdfs.sort(key=lambda p: (p.name, p.stat().st_mtime), reverse=True)
    return pdfs[0]


@app.get("/api/attendance/auto-upload/info")
async def attendance_auto_upload_info():
    """Return the configured watched folder + contents summary (for display in UI)."""
    path_str = str(AUTO_UPLOAD_DIR)
    exists = AUTO_UPLOAD_DIR.exists() and AUTO_UPLOAD_DIR.is_dir()
    latest_name: str | None = None
    pdf_count = 0
    if exists:
        try:
            pdfs = [p for p in AUTO_UPLOAD_DIR.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"]
            pdf_count = len(pdfs)
            picked = _pick_latest_pdf_in(AUTO_UPLOAD_DIR)
            latest_name = picked.name if picked else None
        except Exception:
            pass
    return {
        "path": path_str,
        "exists": exists,
        "pdf_count": pdf_count,
        "latest_filename": latest_name,
        "env_override": "ATTENDANCE_AUTO_UPLOAD_DIR",
    }


@app.post("/api/attendance/auto-upload")
async def attendance_auto_upload(save: bool = False):
    """Preview (and optionally save) the most-recent PDF from the watched folder.

    Response mirrors /api/preview-multiple for a single file when save=False,
    and additionally saves the records to the DB when save=True.
    """
    if not AUTO_UPLOAD_DIR.exists() or not AUTO_UPLOAD_DIR.is_dir():
        raise HTTPException(
            status_code=404,
            detail=f"Watched folder not reachable: {AUTO_UPLOAD_DIR}. "
                   f"Mount the Windows share or set ATTENDANCE_AUTO_UPLOAD_DIR.",
        )

    picked = _pick_latest_pdf_in(AUTO_UPLOAD_DIR)
    if picked is None:
        raise HTTPException(status_code=404, detail=f"No PDF files found in {AUTO_UPLOAD_DIR}.")

    # Parse from the filesystem path directly — no re-upload needed.
    try:
        records = apply_employee_roster(parse_pdf_data(picked))
        metadata = extract_pdf_metadata(picked)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to parse {picked.name}: {exc}") from exc

    record_date = metadata.get("record_date")
    pack_count = metadata.get("number_of_packs")
    file_size = picked.stat().st_size

    preview_data = build_preview_payload(
        picked.name,
        file_size,
        records,
        file_count=1,
        preview_filename=picked.name,
    )
    preview_data["record_date"] = record_date.isoformat() if record_date else None
    preview_data["number_of_packs"] = pack_count
    preview_data["picked_filename"] = picked.name
    preview_data["picked_size"] = file_size
    preview_data["files"] = [
        {
            "filename": picked.name,
            "total_records": len(records),
            "records_with_data": count_records_with_data(records),
            "record_date": record_date.isoformat() if record_date else None,
            "number_of_packs": pack_count,
        }
    ]

    if save:
        mismatches = find_attendance_mismatches(record_date, records)
        excel_filename, _excel_path, records_processed, batch_id = export_records_to_excel(
            picked.name,
            records,
            record_date=record_date,
        )
        if record_date is not None and pack_count is not None:
            upsert_pack_count_for_date(record_date, pack_count, source=picked.name)
        preview_data["saved"] = True
        preview_data["records_processed"] = records_processed
        preview_data["batch_id"] = batch_id
        preview_data["excel_filename"] = excel_filename
        preview_data["download_url"] = build_download_url(excel_filename)
        preview_data["mismatches"] = mismatches
        preview_data["mismatch_count"] = len(mismatches)
    else:
        preview_data["saved"] = False

    return preview_data


@app.post("/api/convert")
async def convert_pdf(file: UploadFile = File(...)):
    """
    Convert PDF to Excel
    Returns Excel file for download
    """
    try:
        original_name, _file_size, records, metadata = await parse_uploaded_pdf(file)
        record_date = metadata.get("record_date")
        pack_count = metadata.get("number_of_packs")

        # Check mismatches against any rows already saved for this date BEFORE we overwrite them.
        mismatches = find_attendance_mismatches(record_date, records)

        excel_filename, _excel_path, records_processed, batch_id = export_records_to_excel(
            original_name,
            records,
            record_date=record_date,
        )

        if record_date is not None and pack_count is not None:
            upsert_pack_count_for_date(record_date, pack_count, source=original_name)

        return {
            "status": "success",
            "filename": excel_filename,
            "records_processed": records_processed,
            "roster_records": len(records),
            "batch_id": batch_id,
            "message": "PDFが正常に変換され、Excelファイルが生成されました",
            "download_url": build_download_url(excel_filename),
            "record_date": record_date.isoformat() if record_date else None,
            "number_of_packs": pack_count,
            "mismatches": mismatches,
            "mismatch_count": len(mismatches),
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected error while converting PDF: {exc}") from exc

@app.post("/api/convert-multiple")
async def convert_multiple_pdfs(files: list[UploadFile] = File(...)):
    """Convert multiple PDFs and return one zip bundle of Excel files."""
    if not files:
        raise HTTPException(status_code=400, detail="Please upload at least one PDF file.")

    try:
        exports: list[tuple[str, Path, int]] = []
        per_file_results: list[dict[str, object]] = []
        total_records_processed = 0
        total_mismatch_count = 0

        for file in files:
            original_name, _file_size, records, metadata = await parse_uploaded_pdf(file)
            record_date = metadata.get("record_date")
            pack_count = metadata.get("number_of_packs")

            mismatches = find_attendance_mismatches(record_date, records)
            total_mismatch_count += len(mismatches)

            excel_filename, excel_path, records_processed, _batch_id = export_records_to_excel(
                original_name,
                records,
                record_date=record_date,
            )

            if record_date is not None and pack_count is not None:
                upsert_pack_count_for_date(record_date, pack_count, source=original_name)

            exports.append((excel_filename, excel_path, len(records)))
            total_records_processed += records_processed
            per_file_results.append({
                "source_filename": original_name,
                "export_filename": excel_filename,
                "record_date": record_date.isoformat() if record_date else None,
                "number_of_packs": pack_count,
                "mismatches": mismatches,
                "mismatch_count": len(mismatches),
            })

        bundle_filename = create_bundle_filename()
        bundle_path = EXPORT_DIR / bundle_filename
        with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for excel_filename, excel_path, _row_count in exports:
                archive.write(excel_path, arcname=excel_filename)

        return {
            "status": "success",
            "filename": bundle_filename,
            "file_count": len(exports),
            "records_processed": total_records_processed,
            "message": f"{len(exports)} PDF files were converted and bundled into one ZIP file.",
            "download_url": build_download_url(bundle_filename),
            "files": per_file_results,
            "mismatch_count": total_mismatch_count,
            "timestamp": datetime.now().isoformat(),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected error while converting PDFs: {exc}") from exc

def _process_batch_job(job_id: str) -> None:
    """Worker executed in a BackgroundTasks thread — converts each staged file one at a time."""
    job_dir = BATCH_UPLOAD_DIR / job_id
    try:
        with BATCH_JOBS_LOCK:
            job = BATCH_JOBS.get(job_id)
            if job is None:
                return
            files = list(job.get("files") or [])
            job["status"] = "running"
            job["started_at"] = datetime.now().isoformat()
            job["started_at_ts"] = time.time()

        exports: list[tuple[str, Path]] = []
        total_records = 0
        total_mismatch_count = 0

        for index, entry in enumerate(files):
            _wait_for_resources(job_id)

            _batch_update_file(job_id, index, status="processing")
            _batch_set(job_id, current_index=index, current_file=entry["source_filename"])

            stored_path = Path(entry["stored_path"])
            try:
                records = apply_employee_roster(parse_pdf_data(stored_path))
                metadata = extract_pdf_metadata(stored_path)
                record_date = metadata.get("record_date")
                pack_count = metadata.get("number_of_packs")

                mismatches = find_attendance_mismatches(record_date, records)
                total_mismatch_count += len(mismatches)

                excel_filename, excel_path, records_processed, _batch_id = export_records_to_excel(
                    entry["source_filename"],
                    records,
                    record_date=record_date,
                )

                if record_date is not None and pack_count is not None:
                    upsert_pack_count_for_date(record_date, pack_count, source=entry["source_filename"])

                exports.append((excel_filename, excel_path))
                total_records += records_processed

                _batch_update_file(
                    job_id,
                    index,
                    status="done",
                    export_filename=excel_filename,
                    records_processed=records_processed,
                    record_date=record_date.isoformat() if record_date else None,
                    number_of_packs=pack_count,
                    mismatch_count=len(mismatches),
                    mismatches=mismatches,
                )
            except ValueError as exc:
                _batch_update_file(job_id, index, status="error", error=str(exc))
            except Exception as exc:  # noqa: BLE001
                _batch_update_file(job_id, index, status="error", error=f"unexpected error: {exc}")

            with BATCH_JOBS_LOCK:
                job = BATCH_JOBS.get(job_id)
                if job is not None:
                    job["processed"] = index + 1
                    job["total_mismatch_count"] = total_mismatch_count
                    job["total_records"] = total_records

        # Bundle successful exports into a single zip.
        successful_exports = [pair for pair in exports if pair[1].exists()]
        bundle_filename = None
        if successful_exports:
            bundle_filename = create_bundle_filename()
            bundle_path = EXPORT_DIR / bundle_filename
            with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for excel_filename, excel_path in successful_exports:
                    archive.write(excel_path, arcname=excel_filename)

        finished_at = datetime.now().isoformat()
        with BATCH_JOBS_LOCK:
            job = BATCH_JOBS.get(job_id)
            if job is not None:
                error_count = sum(1 for f in job.get("files") or [] if f.get("status") == "error")
                job["status"] = "done" if error_count == 0 else "done_with_errors"
                job["bundle_filename"] = bundle_filename
                job["download_url"] = build_download_url(bundle_filename) if bundle_filename else None
                job["finished_at"] = finished_at
                job["finished_at_ts"] = time.time()
                job["current_file"] = None
                job["total_mismatch_count"] = total_mismatch_count
                job["total_records"] = total_records
                job["error_count"] = error_count
    except Exception as exc:  # noqa: BLE001
        with BATCH_JOBS_LOCK:
            job = BATCH_JOBS.get(job_id)
            if job is not None:
                job["status"] = "error"
                job["error"] = f"worker crashed: {exc}"
                job["finished_at"] = datetime.now().isoformat()
                job["finished_at_ts"] = time.time()
    finally:
        # Remove staged PDF inputs — the exports live under EXPORT_DIR and are served separately.
        if job_dir.exists():
            shutil.rmtree(job_dir, ignore_errors=True)

@app.post("/api/convert-batch")
async def convert_batch(background_tasks: BackgroundTasks, files: list[UploadFile] = File(...)):
    """Accept a batch of PDFs, stage them to disk, and kick off a background conversion job."""
    _batch_cleanup_expired()

    if not files:
        raise HTTPException(status_code=400, detail="Please upload at least one PDF file.")

    job_id = uuid4().hex
    job_dir = BATCH_UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    staged: list[dict] = []
    total_bytes = 0
    try:
        for file in files:
            original_name = Path(file.filename or "").name
            if not original_name:
                raise HTTPException(status_code=400, detail="One of the uploaded files is missing a filename.")
            if Path(original_name).suffix.lower() != ".pdf":
                raise HTTPException(status_code=400, detail=f"Only PDF files are supported (got '{original_name}').")

            content = await file.read()
            if not content:
                raise HTTPException(status_code=400, detail=f"'{original_name}' is empty.")
            if b"%PDF" not in content[:1024]:
                raise HTTPException(status_code=400, detail=f"'{original_name}' is not a valid PDF.")

            total_bytes += len(content)
            if total_bytes > BATCH_MAX_TOTAL_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"Batch exceeds the {BATCH_MAX_TOTAL_BYTES // (1024 * 1024)} MB limit "
                        f"(reached {total_bytes // (1024 * 1024)} MB while adding '{original_name}')."
                    ),
                )

            stored_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex}.pdf"
            stored_path = job_dir / stored_name
            stored_path.write_bytes(content)

            staged.append({
                "index": len(staged),
                "source_filename": original_name,
                "stored_path": str(stored_path),
                "size_bytes": len(content),
                "status": "queued",
                "export_filename": None,
                "records_processed": 0,
                "record_date": None,
                "number_of_packs": None,
                "mismatch_count": 0,
                "mismatches": [],
                "error": None,
            })
    except HTTPException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Unexpected error while staging uploads: {exc}") from exc

    created_at = datetime.now().isoformat()
    with BATCH_JOBS_LOCK:
        BATCH_JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "files": staged,
            "total_files": len(staged),
            "processed": 0,
            "total_bytes": total_bytes,
            "total_records": 0,
            "total_mismatch_count": 0,
            "error_count": 0,
            "current_index": None,
            "current_file": None,
            "bundle_filename": None,
            "download_url": None,
            "created_at": created_at,
            "created_at_ts": time.time(),
            "started_at": None,
            "started_at_ts": None,
            "finished_at": None,
            "finished_at_ts": None,
            "throttled": False,
            "cpu_percent": None,
            "ram_percent": None,
            "ram_available_mb": None,
            "error": None,
        }

    background_tasks.add_task(_process_batch_job, job_id)

    return {
        "job_id": job_id,
        "status": "queued",
        "total_files": len(staged),
        "total_bytes": total_bytes,
        "max_total_bytes": BATCH_MAX_TOTAL_BYTES,
        "created_at": created_at,
    }

@app.get("/api/convert-batch/{job_id}/status")
async def convert_batch_status(job_id: str):
    """Return a live snapshot of a batch job for the frontend progress panel."""
    snapshot = _batch_snapshot(job_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Batch job not found (it may have expired).")

    # Refresh live CPU/RAM on read so the UI polling gets current values.
    load = _sample_system_load()
    snapshot["cpu_percent"] = load["cpu_percent"]
    snapshot["ram_percent"] = load["ram_percent"]
    snapshot["ram_available_mb"] = load["ram_available_mb"]

    started_ts = snapshot.get("started_at_ts")
    finished_ts = snapshot.get("finished_at_ts")
    if started_ts is not None:
        end_ts = finished_ts if finished_ts is not None else time.time()
        snapshot["elapsed_seconds"] = round(end_ts - started_ts, 2)
    else:
        snapshot["elapsed_seconds"] = 0.0

    return snapshot

@app.get("/api/system/load")
async def system_load():
    """Lightweight system load snapshot used by the dashboard/status pills."""
    return _sample_system_load()

@app.get("/api/download/{filename}")
async def download_export(filename: str):
    """
    Download a generated Excel file or ZIP bundle.
    """
    file_path = get_export_file_path(filename)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    media_type = (
        "application/zip"
        if file_path.suffix.lower() == ".zip"
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    return FileResponse(
        file_path,
        media_type=media_type,
        filename=file_path.name
    )

@app.get("/api/dashboard/summary")
async def dashboard_summary(month: str | None = None):
    """
    Get dashboard summary statistics
    """
    resolved_month = resolve_month(month)
    rows = list_attendance_rows(resolved_month)
    active_rows = [row for row in rows if row["has_data"]]
    working_minutes = [
        minutes
        for minutes in (parse_working_hours_minutes(row["working_hours"]) for row in active_rows)
        if minutes is not None
    ]

    with get_db_connection() as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) AS batch_count, MAX(upload_date) AS latest_upload
                FROM attendance_records
                WHERE month_year = %s
                """,
                (resolved_month,),
            )
            batch_row = cursor.fetchone()

    year, month_value = resolved_month.split("-")
    return {
        "month": resolved_month,
        "total_employees": len({row["employee_code"] for row in active_rows}),
        "total_records": len(active_rows),
        "average_working_hours": format_average_hours(working_minutes),
        "days_in_month": monthrange(int(year), int(month_value))[1],
        "upload_batches": batch_row["batch_count"] if batch_row else 0,
        "latest_upload": batch_row["latest_upload"] if batch_row else None,
    }

@app.get("/api/dashboard/employees")
async def dashboard_employees(month: str | None = None):
    """
    Get all employees with summary
    """
    resolved_month = resolve_month(month)
    rows = list_attendance_rows(resolved_month)
    by_employee: dict[str, dict[str, object]] = {}

    for row in rows:
        if not row["has_data"]:
            continue

        code = row["employee_code"]
        summary = by_employee.setdefault(code, {
            "code": code,
            "name": row["full_name"],
            "days_worked": 0,
            "working_minutes": [],
        })
        summary["days_worked"] = int(summary["days_worked"]) + 1
        minutes = parse_working_hours_minutes(row["working_hours"])
        if minutes is not None:
            summary["working_minutes"].append(minutes)

    employees = []
    for code in [employee["employee_code"] for employee in EMPLOYEE_ROSTER]:
        summary = by_employee.get(code)
        if not summary:
            continue
        employees.append({
            "id": code,
            "code": code,
            "name": summary["name"],
            "days_worked": summary["days_worked"],
            "avg_working_hours": format_average_hours(summary["working_minutes"]),
        })

    return {
        "month": resolved_month,
        "employees": employees,
        "total_count": len(employees),
    }

@app.get("/api/dashboard/employee/{employee_code}")
async def dashboard_employee_detail(employee_code: str, month: str | None = None):
    """
    Get individual employee details
    """
    resolved_month = resolve_month(month)
    rows = [
        row for row in list_attendance_rows(resolved_month)
        if row["employee_code"] == employee_code
    ]
    working_minutes = [
        minutes
        for minutes in (parse_working_hours_minutes(row["working_hours"]) for row in rows)
        if minutes is not None
    ]
    late_count = sum(
        1
        for row in rows
        if row["has_data"] and (time_to_minutes(row["commute_time"]) or 0) > 9 * 60
    )
    early_count = sum(
        1
        for row in rows
        if row["has_data"] and row["leave_time"] and (time_to_minutes(row["leave_time"]) or 0) < 17 * 60
    )

    return {
        "employee_id": employee_code,
        "name": EMPLOYEE_ROSTER_BY_ID.get(employee_code, ""),
        "month": resolved_month,
        "records": [
            {
                "source_filename": row["source_filename"],
                "converted_at": row["converted_at"],
                "commute_time": row["commute_time"],
                "leave_time": row["leave_time"],
                "working_hours": row["working_hours"],
                "has_data": bool(row["has_data"]),
            }
            for row in rows
        ],
        "monthly_data": {
            "total_hours": round(sum(working_minutes) / 60, 2) if working_minutes else 0,
            "average_daily": format_average_hours(working_minutes),
            "late_count": late_count,
            "early_count": early_count,
        }
    }

@app.get("/api/daily-packs/{record_date}")
async def get_daily_packs(record_date: str):
    """Return the pack count saved for a single date, or 0 if none recorded yet."""
    try:
        parsed = datetime.strptime(record_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="record_date must be YYYY-MM-DD") from exc

    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT number_of_packs, note, updated_at FROM daily_packs WHERE record_date = %s",
                (parsed,),
            )
            row = cursor.fetchone()

    if row is None:
        return {"record_date": record_date, "number_of_packs": 0, "note": None, "exists": False}
    return {
        "record_date": record_date,
        "number_of_packs": row[0],
        "note": row[1],
        "updated_at": row[2].isoformat() if row[2] else None,
        "exists": True,
    }


@app.post("/api/daily-packs/extract-pdf")
async def extract_daily_packs_from_pdf(file: UploadFile = File(...)):
    """Extract date, pack count, AND time mismatches from an uploaded PDF without saving.

    The frontend uses this to pre-fill the Daily packs form so the user can review
    the values and decide whether to save them. It also surfaces any time mismatches
    between the PDF rows and the existing database entries for the same date.
    """
    _original_name, file_path, _content = await save_uploaded_pdf(file)
    metadata = extract_pdf_metadata(file_path)
    record_date = metadata.get("record_date")
    pack_count = metadata.get("number_of_packs")

    # Attendance parsing is best-effort here — a production-summary PDF may only
    # contain the pack count and no attendance table, so we must not fail the
    # whole request if parse_pdf_data can't find rows.
    records = []
    parse_error = None
    try:
        records = apply_employee_roster(parse_pdf_data(file_path))
    except ValueError as exc:
        parse_error = str(exc)
    except Exception as exc:  # noqa: BLE001
        parse_error = f"parser error: {exc}"

    mismatches = find_attendance_mismatches(record_date, records) if records else []
    compared_count = sum(1 for r in records if record_has_data(r))

    return {
        "record_date": record_date.isoformat() if record_date else None,
        "number_of_packs": pack_count,
        "found_date": record_date is not None,
        "found_packs": pack_count is not None,
        "compared_count": compared_count,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "parse_error": parse_error,
    }


@app.post("/api/daily-packs/extract-pdf-multi")
async def extract_daily_packs_from_pdfs(files: list[UploadFile] = File(...)):
    """Extract date + pack count + attendance mismatches from several PDFs in one call.

    Mirrors /api/daily-packs/extract-pdf but runs over a batch. Each entry in the
    returned list is self-describing so the frontend can render per-file state and
    let the user bulk-save all successful extractions at once.
    """
    if not files:
        raise HTTPException(status_code=400, detail="Please upload at least one PDF file.")

    results: list[dict] = []
    found_count = 0
    total_mismatch_count = 0

    for file in files:
        original_name = Path(file.filename or "").name or "unnamed.pdf"
        entry: dict = {
            "source_filename": original_name,
            "record_date": None,
            "number_of_packs": None,
            "found_date": False,
            "found_packs": False,
            "compared_count": 0,
            "mismatch_count": 0,
            "mismatches": [],
            "parse_error": None,
            "error": None,
        }
        try:
            _original, file_path, _content = await save_uploaded_pdf(file)
            metadata = extract_pdf_metadata(file_path)
            record_date = metadata.get("record_date")
            pack_count = metadata.get("number_of_packs")

            records = []
            try:
                records = apply_employee_roster(parse_pdf_data(file_path))
            except ValueError as exc:
                entry["parse_error"] = str(exc)
            except Exception as exc:  # noqa: BLE001
                entry["parse_error"] = f"parser error: {exc}"

            mismatches = find_attendance_mismatches(record_date, records) if records else []
            compared_count = sum(1 for r in records if record_has_data(r))

            entry.update({
                "record_date": record_date.isoformat() if record_date else None,
                "number_of_packs": pack_count,
                "found_date": record_date is not None,
                "found_packs": pack_count is not None,
                "compared_count": compared_count,
                "mismatch_count": len(mismatches),
                "mismatches": mismatches,
            })
            if entry["found_date"] and entry["found_packs"]:
                found_count += 1
            total_mismatch_count += len(mismatches)
        except HTTPException as exc:
            entry["error"] = exc.detail if isinstance(exc.detail, str) else "validation failed"
        except Exception as exc:  # noqa: BLE001
            entry["error"] = f"unexpected error: {exc}"

        results.append(entry)

    return {
        "total_files": len(files),
        "extractable_count": found_count,
        "total_mismatch_count": total_mismatch_count,
        "results": results,
    }


@app.post("/api/daily-packs/bulk")
async def upsert_daily_packs_bulk(payload: dict = Body(...)):
    """Upsert many (date, pack count) rows at once — used by the daily packs batch UI.

    Request: {"entries": [{"record_date": "YYYY-MM-DD", "number_of_packs": 123, "note": "..."}, ...]}
    Each entry is validated and persisted independently; the response reports per-entry
    success so the frontend can flag the ones that failed without losing the rest.
    """
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        raise HTTPException(status_code=400, detail="entries must be a non-empty list")

    results: list[dict] = []
    saved_count = 0
    failed_count = 0

    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            for raw in entries:
                record_date = raw.get("record_date") if isinstance(raw, dict) else None
                number_of_packs = raw.get("number_of_packs") if isinstance(raw, dict) else None
                note = raw.get("note") if isinstance(raw, dict) else None

                entry_result: dict = {
                    "record_date": record_date,
                    "saved": False,
                    "number_of_packs": None,
                    "error": None,
                }
                try:
                    if not record_date:
                        raise ValueError("record_date is required")
                    parsed_date = datetime.strptime(record_date, "%Y-%m-%d").date()
                    packs_value = int(number_of_packs)
                    if packs_value < 0:
                        raise ValueError("number_of_packs cannot be negative")

                    cursor.execute(
                        """
                        INSERT INTO daily_packs (record_date, number_of_packs, note)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (record_date) DO UPDATE
                            SET number_of_packs = EXCLUDED.number_of_packs,
                                note = EXCLUDED.note,
                                updated_at = NOW()
                        RETURNING number_of_packs
                        """,
                        (parsed_date, packs_value, note),
                    )
                    row = cursor.fetchone()
                    entry_result["saved"] = True
                    entry_result["number_of_packs"] = row[0]
                    saved_count += 1
                except (TypeError, ValueError) as exc:
                    entry_result["error"] = str(exc)
                    failed_count += 1
                except Exception as exc:  # noqa: BLE001
                    entry_result["error"] = f"database error: {exc}"
                    failed_count += 1

                results.append(entry_result)
        connection.commit()

    return {
        "total": len(entries),
        "saved": saved_count,
        "failed": failed_count,
        "results": results,
    }


@app.post("/api/daily-packs")
async def upsert_daily_packs(payload: dict = Body(...)):
    """Insert or update the pack count for a single date (one row per date)."""
    record_date = payload.get("record_date")
    number_of_packs = payload.get("number_of_packs")
    note = payload.get("note")

    if not record_date:
        raise HTTPException(status_code=400, detail="record_date is required")
    try:
        parsed_date = datetime.strptime(record_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="record_date must be YYYY-MM-DD") from exc
    try:
        packs_value = int(number_of_packs)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="number_of_packs must be an integer") from exc
    if packs_value < 0:
        raise HTTPException(status_code=400, detail="number_of_packs cannot be negative")

    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO daily_packs (record_date, number_of_packs, note)
                VALUES (%s, %s, %s)
                ON CONFLICT (record_date) DO UPDATE
                    SET number_of_packs = EXCLUDED.number_of_packs,
                        note = EXCLUDED.note,
                        updated_at = NOW()
                RETURNING number_of_packs, updated_at
                """,
                (parsed_date, packs_value, note),
            )
            saved = cursor.fetchone()
        connection.commit()

    return {
        "record_date": record_date,
        "number_of_packs": saved[0],
        "updated_at": saved[1].isoformat() if saved[1] else None,
        "saved": True,
    }


@app.get("/api/productivity")
async def productivity(range: str = "week", end: str | None = None):
    """
    Labor productivity (packs / working hours) aggregated by day and section.
    Returns current + previous period of the same length for comparison.
    """
    range_days = {"day": 1, "week": 7, "month": 30, "3month": 90}
    if range not in range_days:
        raise HTTPException(status_code=400, detail="range must be day|week|month|3month")
    n = range_days[range]

    if end:
        try:
            end_dt = datetime.strptime(end, "%Y-%m-%d").date()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="end must be YYYY-MM-DD") from exc
    else:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT MAX(record_date) FROM attendance_records")
                row = cursor.fetchone()
                end_dt = row[0] if row and row[0] else datetime.now().date()

    cur_start = end_dt - timedelta(days=n - 1)
    prev_end = cur_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=n - 1)

    def aggregate(start_date, end_date):
        with get_db_connection() as connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT DISTINCT ON (record_date, personal_code)
                           record_date, personal_code, working_hours
                    FROM attendance_records
                    WHERE record_date BETWEEN %s AND %s
                    ORDER BY record_date, personal_code, upload_date DESC
                    """,
                    (start_date, end_date),
                )
                att_rows = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT record_date, number_of_packs
                    FROM daily_packs
                    WHERE record_date BETWEEN %s AND %s
                    """,
                    (start_date, end_date),
                )
                pack_rows = cursor.fetchall()

        daily = {}
        day = start_date
        while day <= end_date:
            daily[day] = {"packs": 0, "s1_min": 0, "s2_min": 0}
            day += timedelta(days=1)

        for r in pack_rows:
            if r["record_date"] in daily:
                daily[r["record_date"]]["packs"] = int(r["number_of_packs"] or 0)

        for r in att_rows:
            minutes = parse_working_hours_minutes(r["working_hours"]) or 0
            if minutes <= 0:
                continue
            sid = SECTION_OF_CODE.get(r["personal_code"], 0)
            bucket = daily.get(r["record_date"])
            if bucket is None:
                continue
            if sid == 1:
                bucket["s1_min"] += minutes
            elif sid == 2:
                bucket["s2_min"] += minutes

        labels, packs, s1_lp, s2_lp, comb_lp = [], [], [], [], []
        s1_hours_series, s2_hours_series, comb_hours_series = [], [], []
        tot_packs = tot_s1 = tot_s2 = 0
        day = start_date
        while day <= end_date:
            b = daily[day]
            s1_h = b["s1_min"] / 60
            s2_h = b["s2_min"] / 60
            comb_h = s1_h + s2_h
            labels.append(day.isoformat())
            packs.append(b["packs"])
            s1_hours_series.append(round(s1_h, 2))
            s2_hours_series.append(round(s2_h, 2))
            comb_hours_series.append(round(comb_h, 2))
            s1_lp.append(round(b["packs"] / s1_h, 2) if s1_h > 0 else 0)
            s2_lp.append(round(b["packs"] / s2_h, 2) if s2_h > 0 else 0)
            comb_lp.append(round(b["packs"] / comb_h, 2) if comb_h > 0 else 0)
            tot_packs += b["packs"]
            tot_s1 += b["s1_min"]
            tot_s2 += b["s2_min"]
            day += timedelta(days=1)

        tot_s1_h = tot_s1 / 60
        tot_s2_h = tot_s2 / 60
        tot_comb_h = tot_s1_h + tot_s2_h
        summary = {
            "total_packs": tot_packs,
            "total_hours_s1": round(tot_s1_h, 2),
            "total_hours_s2": round(tot_s2_h, 2),
            "total_hours_combined": round(tot_comb_h, 2),
            "lp_s1": round(tot_packs / tot_s1_h, 2) if tot_s1_h > 0 else 0,
            "lp_s2": round(tot_packs / tot_s2_h, 2) if tot_s2_h > 0 else 0,
            "lp_combined": round(tot_packs / tot_comb_h, 2) if tot_comb_h > 0 else 0,
        }
        return {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "summary": summary,
            "series": {
                "labels": labels,
                "packs": packs,
                "hours_s1": s1_hours_series,
                "hours_s2": s2_hours_series,
                "hours_combined": comb_hours_series,
                "lp_s1": s1_lp,
                "lp_s2": s2_lp,
                "lp_combined": comb_lp,
            },
        }

    return {
        "range": range,
        "current": aggregate(cur_start, end_dt),
        "previous": aggregate(prev_start, prev_end),
    }


@app.get("/api/temp-staff/{record_date}")
async def get_temp_staff(record_date: str):
    """
    Console v3.0 — Tab 2 フルキャスト: fetch saved temp-staff rows for one date.
    Frontend calls this whenever the shift date changes so the form reflects the DB.
    """
    try:
        parsed_date = datetime.strptime(record_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="record_date must be YYYY-MM-DD") from exc

    with get_db_connection() as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT id, company, headcount, start_time, leave_time,
                       hours_per_person, total_hours, note, created_at
                FROM temp_staff
                WHERE record_date = %s
                ORDER BY id
                """,
                (parsed_date,),
            )
            rows = [
                {
                    "id": r["id"],
                    "company": r["company"],
                    "headcount": r["headcount"],
                    "start_time": r["start_time"],
                    "leave_time": r["leave_time"],
                    "hours_per_person": float(r["hours_per_person"]) if r["hours_per_person"] is not None else 0.0,
                    "total_hours": float(r["total_hours"]) if r["total_hours"] is not None else 0.0,
                    "note": r["note"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                }
                for r in cursor.fetchall()
            ]
    total_people = sum(r["headcount"] for r in rows)
    total_hours = sum(r["total_hours"] for r in rows)
    return {
        "record_date": record_date,
        "rows": rows,
        "total_people": total_people,
        "total_hours": round(total_hours, 2),
    }


@app.post("/api/temp-staff")
async def save_temp_staff(payload: dict = Body(...)):
    """
    Console v3.0 — Tab 2 フルキャスト: replace all rows for a given shift date.
    Request: {"record_date": "YYYY-MM-DD",
              "rows": [{"headcount": int, "start_time": "HH:MM", "leave_time": "HH:MM",
                        "company": "フルキャスト"?, "note": str?}, ...]}
    The endpoint deletes any existing rows for that date and inserts the new set.
    hours_per_person and total_hours are computed server-side via calculate_temp_staff_hours().
    """
    record_date = payload.get("record_date")
    rows_in = payload.get("rows")
    if not record_date:
        raise HTTPException(status_code=400, detail="record_date is required")
    try:
        parsed_date = datetime.strptime(record_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="record_date must be YYYY-MM-DD") from exc
    if not isinstance(rows_in, list):
        raise HTTPException(status_code=400, detail="rows must be a list (pass empty list to clear)")

    cleaned: list[tuple] = []
    for raw in rows_in:
        if not isinstance(raw, dict):
            continue
        try:
            headcount = int(raw.get("headcount"))
        except (TypeError, ValueError):
            continue
        if headcount <= 0:
            continue
        start_time = (raw.get("start_time") or "").strip()
        leave_time = (raw.get("leave_time") or "").strip()
        if not re.match(r"^\d{1,2}:\d{2}$", start_time) or not re.match(r"^\d{1,2}:\d{2}$", leave_time):
            continue
        hours_per_person = calculate_temp_staff_hours(start_time, leave_time)
        total_hours = round(headcount * hours_per_person, 2)
        company = (raw.get("company") or "フルキャスト").strip() or "フルキャスト"
        note = raw.get("note")
        cleaned.append((parsed_date, company, headcount, start_time, leave_time,
                        hours_per_person, total_hours, note))

    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM temp_staff WHERE record_date = %s", (parsed_date,))
            if cleaned:
                cursor.executemany(
                    """
                    INSERT INTO temp_staff
                        (record_date, company, headcount, start_time, leave_time,
                         hours_per_person, total_hours, note)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    cleaned,
                )
        connection.commit()

    total_people = sum(row[2] for row in cleaned)
    total_hours = round(sum(row[6] for row in cleaned), 2)
    return {
        "record_date": record_date,
        "saved_rows": len(cleaned),
        "total_people": total_people,
        "total_hours": total_hours,
    }


# TODO (v3.0 /console backend): planned endpoints not yet implemented:
#   - POST /api/attendance/save          save previewed PDF batch to DB without Excel
#   - GET  /api/summary/{record_date}    aggregated per-dept productivity + target line
#   - GET  /summary                      B4 portrait Summarizing Report page
# For v1 the console reuses /api/convert-multiple (saves + Excel) for Tab 1 and
# hides the Excel download from the UI. Summarizing Report button links to /summary
# which will 404 until the page is built.


@app.get("/api/dashboard/months")
async def dashboard_months():
    """
    Get available months with data
    """
    with get_db_connection() as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                "SELECT DISTINCT month_year FROM attendance_records ORDER BY month_year DESC"
            )
            rows = cursor.fetchall()

    months = [row["month_year"] for row in rows]
    return {
        "available_months": months,
        "latest_month": months[0] if months else None,
    }

# Serve static files
if (BASE_DIR / "static").exists():
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8002)
