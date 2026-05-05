#!/usr/bin/env python3
"""doctor.py — periodic internal health check.

Runs every 5 hours via the attendance-doctor.timer systemd unit. Reads the DB,
sidecar JSON configs, and watched folders; reports anything inconsistent into
logs/internal_health_logs.log. Optionally triggers ingestion for files sitting
in a watched folder that never made it to done/.

Exit code is always 0 — this is a watcher, not a gate.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
import urllib.request
from datetime import datetime
from pathlib import Path

import psycopg2

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "internal_health_logs.log"

DATABASE = {
    "host": os.getenv("ATTENDANCE_DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("ATTENDANCE_DB_PORT", "5432")),
    "dbname": os.getenv("ATTENDANCE_DB_NAME", "attendance_db"),
    "user": os.getenv("ATTENDANCE_DB_USER", "attendance"),
    "password": os.getenv("ATTENDANCE_DB_PASSWORD", "attendance2026"),
}

API_BASE = os.getenv("ATTENDANCE_API_BASE", "http://127.0.0.1:8002")
API_KEY = os.getenv("ATTENDANCE_DOCTOR_KEY")  # optional; if unset, sweepers are skipped
AUTO_PROCESS = os.getenv("ATTENDANCE_DOCTOR_AUTO_PROCESS", "1") == "1"

WATCHED = {
    "attendance":  BASE_DIR / "auto_uploads" / "attendance",
    "daily_packs": BASE_DIR / "auto_uploads" / "daily_packs",
}

EXPECTED_TABLES = [
    "attendance_records", "upload_batches", "uploaded_file_registry",
    "daily_packs", "daily_pack_items", "temp_staff", "production_plan",
]

EXPECTED_CONFIGS = {
    "employee_roster.json":    list,
    "sections.json":           dict,
    "nickname_map.json":       dict,
    "production_rates.json":   dict,
    "auto_upload_config.json": dict,
    "api_keys.json":           dict,
    "admin_config.json":       dict,
}


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_db_health(report: list[str]) -> None:
    """Row counts per table + latest row date where applicable."""
    try:
        with psycopg2.connect(**DATABASE) as conn, conn.cursor() as cur:
            for tbl in EXPECTED_TABLES:
                cur.execute(f"SELECT COUNT(*) FROM {tbl}")
                count = cur.fetchone()[0]
                report.append(f"  table {tbl:<25} rows={count}")
    except Exception as e:
        report.append(f"  ERROR db_health: {e}")


def check_registry_consistency(report: list[str]) -> None:
    """Find uploaded_file_registry rows claiming status='loaded' for a date
    that has no matching rows in the corresponding data table."""
    try:
        with psycopg2.connect(**DATABASE) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT sha256, file_type, target_date FROM uploaded_file_registry "
                "WHERE status = 'loaded' AND target_date IS NOT NULL"
            )
            orphans = []
            for sha, ftype, tdate in cur.fetchall():
                if ftype == "attendance":
                    cur.execute(
                        "SELECT COUNT(*) FROM attendance_records WHERE record_date = %s",
                        (tdate,),
                    )
                else:
                    cur.execute(
                        "SELECT COUNT(*) FROM daily_pack_items WHERE production_date = %s",
                        (tdate,),
                    )
                    if cur.fetchone()[0] == 0:
                        cur.execute(
                            "SELECT COUNT(*) FROM daily_packs WHERE record_date = %s",
                            (tdate,),
                        )
                if cur.fetchone()[0] == 0:
                    orphans.append((sha[:12], ftype, tdate))
            if orphans:
                report.append(f"  WARNING registry_orphans={len(orphans)}: {orphans}")
            else:
                report.append("  registry_consistency OK")
    except Exception as e:
        report.append(f"  ERROR registry_consistency: {e}")


def check_sidecar_configs(report: list[str]) -> None:
    """Each expected JSON file must exist, parse, and be the right top-level type."""
    for name, expected_type in EXPECTED_CONFIGS.items():
        path = BASE_DIR / name
        if not path.exists():
            report.append(f"  MISSING config {name}")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            report.append(f"  INVALID config {name}: {e}")
            continue
        if not isinstance(data, expected_type):
            report.append(f"  WRONG_TYPE config {name}: expected {expected_type.__name__}")
            continue
        size = len(data) if hasattr(data, "__len__") else "?"
        report.append(f"  config {name:<28} ok (entries={size})")


def check_unprocessed_files(report: list[str]) -> list[tuple[str, Path]]:
    """List files sitting in a watched folder that never made it to done/.
    Returns (kind, path) tuples for the caller to optionally trigger."""
    pending: list[tuple[str, Path]] = []
    for kind, folder in WATCHED.items():
        if not folder.exists():
            report.append(f"  watched {kind:<12} MISSING ({folder})")
            continue
        files = [p for p in folder.iterdir() if p.is_file()]
        if not files:
            report.append(f"  watched {kind:<12} clean")
            continue
        report.append(f"  watched {kind:<12} unprocessed={len(files)}")
        for p in files:
            report.append(f"    pending: {p.name}")
            pending.append((kind, p))
    return pending


def trigger_ingest(pending: list[tuple[str, Path]], report: list[str]) -> None:
    """Hit the existing auto-extract endpoints over loopback so the same
    code path runs as a normal upload. Idempotent — re-runs are safe.
    Skipped silently if AUTO_PROCESS is off or no API key is configured."""
    if not AUTO_PROCESS or not API_KEY:
        report.append("  auto_process: disabled (set ATTENDANCE_DOCTOR_AUTO_PROCESS=1 + ATTENDANCE_DOCTOR_KEY)")
        return
    if not pending:
        return
    kinds = {k for k, _ in pending}
    endpoints: list[tuple[str, str]] = []
    if "attendance" in kinds:
        endpoints.append(("attendance", "/api/attendance/auto-upload?save=true"))
    if "daily_packs" in kinds:
        endpoints.append(("daily_packs", "/api/daily-packs/auto-extract"))
        endpoints.append(("daily_packs_excel", "/api/daily-packs/auto-extract-excel"))
    for label, path in endpoints:
        try:
            req = urllib.request.Request(
                API_BASE + path, method="POST",
                headers={"X-API-Key": API_KEY, "Accept": "application/json"},
                data=b"",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                report.append(f"  triggered {label}: HTTP {resp.status}")
        except Exception as e:
            report.append(f"  trigger {label} FAILED: {e}")


def check_routine_events(report: list[str]) -> None:
    """Catch-all hook for additional checks. Add new checks below as the system grows."""
    # Disk usage on watched folders
    for kind, folder in WATCHED.items():
        if folder.exists():
            done = folder / "done"
            done_count = sum(1 for _ in done.iterdir()) if done.exists() else 0
            report.append(f"  done_files {kind:<12} archived={done_count}")


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    started = datetime.now().isoformat(timespec="seconds")
    report: list[str] = [f"=== doctor run {started} ==="]
    try:
        report.append("[db_health]")
        check_db_health(report)
        report.append("[registry_consistency]")
        check_registry_consistency(report)
        report.append("[sidecar_configs]")
        check_sidecar_configs(report)
        report.append("[unprocessed_files]")
        pending = check_unprocessed_files(report)
        report.append("[ingest_trigger]")
        trigger_ingest(pending, report)
        report.append("[routine_events]")
        check_routine_events(report)
    except Exception:
        report.append("FATAL:")
        report.append(traceback.format_exc())
    report.append(f"=== end {datetime.now().isoformat(timespec='seconds')} ===\n")

    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
