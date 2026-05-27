#!/usr/bin/env python3
"""doctor.py — periodic internal health check.

Runs every 5 hours via the attendance-doctor.timer systemd unit. Reads the DB,
sidecar JSON configs, and watched folders; reports anything inconsistent into
logs/internal_health_logs.log. Optionally triggers ingestion for files sitting
in a watched folder that never made it to done/.

Exit code is always 0 — this is a watcher, not a gate.

Tasks (in order):
  [db_health]            row counts per tracked table
  [registry_consistency] uploaded_file_registry orphans
  [sidecar_configs]      JSON config existence + parse + type
  [unprocessed_files]    files in watched folders still outside done/
  [ingest_trigger]       auto-ingest stuck files (PDF + xlsm two-step save)
  [db_clone]             pg_dump → gzip → SD + USB when row count changed
  [routine_events]       done/ archive counts
"""
from __future__ import annotations

import gzip
import json
import os
import re
import subprocess
import sys
import traceback
import urllib.error
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

# DB clone targets (removable media). Doctor skips a target whose folder is
# missing (e.g. SD card pulled, USB unmounted) — never blocks on it.
CLONE_TARGETS = [
    Path("/media/pi/sd-root/db_clones"),
    Path("/media/pi/MyData/db_clones"),
]
CLONE_RETAIN = 7  # keep this many .sql.gz files per target; older ones get pruned
LAST_CLONE_STATE = LOG_DIR / "last_db_clone.json"


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


# ---- ingest trigger helpers ------------------------------------------------

def _extract_date_from_xlsx_name(name: str) -> str | None:
    """Pull YYYY-MM-DD out of a daily-pack xlsm filename.
    Handles both full-width ('夜勤用日報２６．０５．２６.xlsm') and ASCII forms.
    Returns None if no date pattern found."""
    z2h = str.maketrans("０１２３４５６７８９", "0123456789")
    m = re.search(r"([０-９]{2})．([０-９]{2})．([０-９]{2})", name)
    if m:
        yy, mm, dd = (g.translate(z2h) for g in m.groups())
        return f"20{yy}-{mm}-{dd}"
    m = re.search(r"(\d{4})[.\-_](\d{2})[.\-_](\d{2})", name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"(\d{2})[.\-_](\d{2})[.\-_](\d{2})", name)
    if m:
        yy, mm, dd = m.groups()
        return f"20{yy}-{mm}-{dd}"
    return None


def _post(path: str, body: bytes | None = None, headers_extra: dict | None = None,
          timeout: int = 120) -> tuple[int, bytes]:
    """Loopback POST helper. Returns (status, body_bytes). Raises only on transport errors."""
    headers = {"X-API-Key": API_KEY, "Accept": "application/json"}
    if headers_extra:
        headers.update(headers_extra)
    req = urllib.request.Request(API_BASE + path, method="POST",
                                 headers=headers, data=body or b"")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        try:
            payload = e.read()
        except Exception:
            payload = b""
        return e.code, payload


def _trigger_excel_chain(xlsx_path: Path, report: list[str]) -> None:
    """auto-extract-excel returns a preview only (does NOT save to DB).
    Chain it into save-excel-batch so xlsm files actually land in daily_pack_items.
    Targets the file's encoded date so a multi-file folder picks the right one."""
    date_str = _extract_date_from_xlsx_name(xlsx_path.name)
    extract_path = "/api/daily-packs/auto-extract-excel"
    if date_str:
        extract_path += f"?date={date_str}"

    status, body = _post(extract_path)
    if status != 200:
        report.append(f"  excel-chain extract {xlsx_path.name} FAILED: HTTP {status} {body[:160].decode('utf-8','replace')}")
        return
    try:
        preview = json.loads(body.decode("utf-8"))
    except Exception as e:
        report.append(f"  excel-chain extract {xlsx_path.name} FAILED: bad JSON ({e})")
        return

    meta = preview.get("meta") or {}
    products = preview.get("products") or []
    start = (preview.get("start") or {}).get("start_time") or "17:00"
    pdate = meta.get("production_date")
    if not products or not pdate:
        report.append(f"  excel-chain {xlsx_path.name}: extract OK but no products/date — skipped save")
        return

    save_payload = {
        "production_date": pdate,
        "products": products,
        "start_time": start,
        "source_filename": preview.get("source_filename") or xlsx_path.name,
        "input_by": "attendance-doctor",
    }
    save_body = json.dumps(save_payload).encode("utf-8")
    status, body = _post(
        "/api/daily-packs/save-excel-batch",
        body=save_body,
        headers_extra={"Content-Type": "application/json"},
    )
    if status == 200:
        report.append(f"  excel-chain {xlsx_path.name}: extract+save OK (production_date={pdate}, products={len(products)})")
    else:
        report.append(f"  excel-chain save {xlsx_path.name} FAILED: HTTP {status} {body[:160].decode('utf-8','replace')}")


def _trigger_simple(label: str, path: str, report: list[str]) -> None:
    """POST to a single endpoint and log the result. 404 'no matching file'
    is treated as informational, not an error — folder may just have no
    files of this kind right now."""
    status, body = _post(path)
    if status == 200:
        report.append(f"  triggered {label}: HTTP 200")
    elif status == 404:
        report.append(f"  triggered {label}: no matching file (404)")
    else:
        report.append(f"  trigger {label} FAILED: HTTP {status} {body[:160].decode('utf-8','replace')}")


def trigger_ingest(pending: list[tuple[str, Path]], report: list[str]) -> None:
    """Re-drive stuck watched files through the normal upload endpoints over
    loopback. Idempotent — re-runs are safe."""
    if not AUTO_PROCESS or not API_KEY:
        report.append("  auto_process: disabled (set ATTENDANCE_DOCTOR_AUTO_PROCESS=1 + ATTENDANCE_DOCTOR_KEY)")
        return
    if not pending:
        return

    has_attendance = any(k == "attendance" for k, _ in pending)
    daily_pack_pdfs = [p for k, p in pending if k == "daily_packs" and p.suffix.lower() == ".pdf"]
    daily_pack_xlsx = [p for k, p in pending if k == "daily_packs" and p.suffix.lower() in (".xlsx", ".xlsm")]

    if has_attendance:
        # auto-upload?save=true is a single-call extract+save — sufficient on its own.
        _trigger_simple("attendance", "/api/attendance/auto-upload?save=true", report)

    if daily_pack_pdfs:
        # auto-extract returns preview only; full save requires operator confirm in the UI.
        # We surface that the file was previewed; operator still needs to confirm.
        _trigger_simple("daily_packs_pdf", "/api/daily-packs/auto-extract", report)

    for xlsx_path in daily_pack_xlsx:
        _trigger_excel_chain(xlsx_path, report)


# ---- DB clone task ---------------------------------------------------------

def _load_clone_state() -> dict:
    if not LAST_CLONE_STATE.exists():
        return {}
    try:
        return json.loads(LAST_CLONE_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_clone_state(state: dict) -> None:
    LAST_CLONE_STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def check_db_clone(report: list[str]) -> None:
    """Clone the Postgres DB to SD card + USB whenever the combined row count
    across tracked tables differs from the last successful clone. Per-target
    failure (missing mount, read-only FS) is non-fatal — other target still
    runs, and the next tick retries the failed one."""
    try:
        with psycopg2.connect(**DATABASE) as conn, conn.cursor() as cur:
            total = 0
            for tbl in EXPECTED_TABLES:
                cur.execute(f"SELECT COUNT(*) FROM {tbl}")
                total += cur.fetchone()[0]
    except Exception as e:
        report.append(f"  db_clone ERROR row-count: {e}")
        return

    state = _load_clone_state()
    last_total = state.get("total_rows")
    if last_total == total and state.get("targets_ok"):
        report.append(f"  db_clone: skipped (total_rows={total} unchanged since {state.get('cloned_at','?')})")
        return

    # pg_dump → gzip in memory (~200KB-1MB for this DB, fine).
    env = os.environ.copy()
    env["PGPASSWORD"] = DATABASE["password"]
    cmd = [
        "pg_dump",
        "-h", DATABASE["host"],
        "-p", str(DATABASE["port"]),
        "-U", DATABASE["user"],
        "-d", DATABASE["dbname"],
        "--no-owner", "--no-privileges",
    ]
    try:
        proc = subprocess.run(cmd, env=env, capture_output=True, timeout=300)
    except Exception as e:
        report.append(f"  db_clone ERROR pg_dump: {e}")
        return
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace")[:200].strip()
        report.append(f"  db_clone ERROR pg_dump rc={proc.returncode}: {err}")
        return
    gz_bytes = gzip.compress(proc.stdout)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"attendance_db_{stamp}.sql.gz"

    targets_ok: list[str] = []
    targets_err: list[str] = []
    for tgt in CLONE_TARGETS:
        if not tgt.exists():
            targets_err.append(f"{tgt}: not mounted")
            continue
        try:
            (tgt / filename).write_bytes(gz_bytes)
            # retention: prune oldest beyond CLONE_RETAIN
            clones = sorted(tgt.glob("attendance_db_*.sql.gz"))
            for old in clones[:-CLONE_RETAIN]:
                try:
                    old.unlink()
                except Exception:
                    pass
            targets_ok.append(str(tgt))
        except Exception as exc:
            targets_err.append(f"{tgt}: {exc}")

    if not targets_ok:
        report.append(f"  db_clone FAILED: all targets failed — {'; '.join(targets_err)}")
        # Don't update state — next tick will retry.
        return

    delta = total - (last_total or 0)
    msg = (f"  db_clone OK: {filename} ({len(gz_bytes):,}B) → "
           f"{len(targets_ok)} target(s) [delta_rows={delta:+d}, total={total}]")
    if targets_err:
        msg += f" (skipped: {'; '.join(targets_err)})"
    report.append(msg)

    _save_clone_state({
        "total_rows": total,
        "cloned_at": datetime.now().isoformat(timespec="seconds"),
        "filename": filename,
        "size_bytes": len(gz_bytes),
        "targets_ok": targets_ok,
        "targets_err": targets_err,
    })


def check_routine_events(report: list[str]) -> None:
    """Catch-all hook for additional checks. Add new checks below as the system grows."""
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
        report.append("[db_clone]")
        check_db_clone(report)
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
