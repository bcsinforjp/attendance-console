"""
seed_demo_data.py — generate 3 months of realistic demo data for the
Attendance Operations Console / Summary dashboard.

Pattern matches real production operations:
  - Mon–Fri: full staff (92–98% present), 8.0–9.5 working hours
  - Saturday: 30–45% of staff on half-day shifts (on ~half of Saturdays)
  - Sunday: no records
  - Holidays (approximate list) skipped like Sunday
  - Daily pack counts tuned so Section1 LP lands around 75–95 P/h,
    Section2 LP around 30–42 P/h, Combined LP around 22–28 P/h
    (i.e. near the targets S1=85, S2=35, Combined=25)
  - Monday + month-end days run hotter; Friday and post-holiday a touch cooler
  - A フルキャスト (temp-staff) bucket of 3–7 workers is added on ~30% of busy days

Usage (run on the Pi, or anywhere the DB is reachable):

    # default: last 92 days ending today
    python3 seed_demo_data.py

    # explicit range
    python3 seed_demo_data.py --start 2026-01-20 --end 2026-04-20

    # replace existing demo rows for that window (safe — only touches
    # file_name starting with 'DEMO-SEED-'; real uploads are untouched)
    python3 seed_demo_data.py --start 2026-01-20 --end 2026-04-20 --replace

    # DRY RUN — show what would be written, touch nothing
    python3 seed_demo_data.py --dry-run

Environment:
    ATTENDANCE_DB_HOST / PORT / NAME / USER / PASSWORD (same as main.py)
"""

from __future__ import annotations

import argparse
import json
import os
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import psycopg2

# ------------------------------------------------------------------
# Config — mirrors main.py env defaults
# ------------------------------------------------------------------
BASE = Path(__file__).resolve().parent
ROSTER_FILE = BASE / "employee_roster.json"
SECTIONS_FILE = BASE / "sections.json"

DB = dict(
    host=os.getenv("ATTENDANCE_DB_HOST", "127.0.0.1"),
    port=int(os.getenv("ATTENDANCE_DB_PORT", "5432")),
    dbname=os.getenv("ATTENDANCE_DB_NAME", "attendance_db"),
    user=os.getenv("ATTENDANCE_DB_USER", "attendance"),
    password=os.getenv("ATTENDANCE_DB_PASSWORD", "attendance2026"),
)

DEMO_FILE_PREFIX = "DEMO-SEED-"  # all inserted rows carry this file_name marker

# Target LP values (match summary page).
TARGET_S1 = 85.0
TARGET_S2 = 35.0
TARGET_COMBINED = 25.0

# Approximate Japanese public holidays 2025-11 .. 2026-05.
# Kept small — good enough for "these days had no records" realism.
APPROX_HOLIDAYS = {
    date(2025, 11, 3), date(2025, 11, 23), date(2025, 11, 24),
    date(2025, 12, 29), date(2025, 12, 30), date(2025, 12, 31),
    date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 12),
    date(2026, 2, 11), date(2026, 2, 23),
    date(2026, 3, 20),
    date(2026, 4, 29), date(2026, 5, 3), date(2026, 5, 4), date(2026, 5, 5), date(2026, 5, 6),
}


@dataclass
class Employee:
    code: str
    name: str
    section: int  # 1 or 2
    # simple per-person profile so each employee has consistent habits
    base_start_min: int   # minutes past midnight, e.g. 8:30 -> 510
    base_hours: float     # typical shift length (8.0-9.0)


def load_roster() -> list[Employee]:
    with ROSTER_FILE.open(encoding="utf-8") as fh:
        roster = json.load(fh)
    with SECTIONS_FILE.open(encoding="utf-8") as fh:
        sections = json.load(fh)
    code_to_section: dict[str, int] = {}
    for sec in sections["sections"]:
        for code in sec["codes"]:
            code_to_section[code] = sec["id"]

    rng = random.Random("profile-seed")  # stable per-employee profile
    out: list[Employee] = []
    for r in roster:
        code = r["employee_code"]
        sid = code_to_section.get(code)
        if not sid:
            continue
        # start between 08:00 and 08:45, 5-min grid
        base_start_min = rng.choice([480, 485, 490, 495, 500, 505, 510, 515, 520, 525])
        base_hours = round(rng.uniform(8.0, 9.2), 2)
        out.append(Employee(code=code, name=r["name"], section=sid,
                             base_start_min=base_start_min, base_hours=base_hours))
    return out


# ------------------------------------------------------------------
# Day-shape helpers
# ------------------------------------------------------------------
def is_workday(d: date) -> bool:
    if d.weekday() == 6:  # Sunday
        return False
    if d in APPROX_HOLIDAYS:
        return False
    return True


def day_intensity(d: date, rng: random.Random) -> float:
    """Fraction multiplier for pack count. 1.0 = typical, >1 busy, <1 light."""
    wd = d.weekday()  # 0=Mon ... 6=Sun
    base = {0: 1.08, 1: 1.04, 2: 1.02, 3: 0.98, 4: 0.94, 5: 0.55}.get(wd, 0.0)
    # month-end push (last 3 weekdays of the month): +5%
    next_day = d + timedelta(days=1)
    if next_day.month != d.month:
        base *= 1.05
    # random wobble ±8%
    base *= rng.uniform(0.92, 1.08)
    return base


def present_fraction(d: date, rng: random.Random) -> float:
    wd = d.weekday()
    if wd == 5:  # Saturday — only some people come in
        return rng.uniform(0.30, 0.45)
    return rng.uniform(0.92, 0.98)


def minutes_to_hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def hours_to_working_hours_str(h: float) -> str:
    """Produce '8:30 hr' style to match the real upload format."""
    total_min = int(round(h * 60))
    hh = total_min // 60
    mm = total_min % 60
    return f"{hh}:{mm:02d} hr"


# ------------------------------------------------------------------
# One-day generation
# ------------------------------------------------------------------
def gen_day(d: date, employees: list[Employee], rng: random.Random) -> tuple[list[dict], int, list[dict]]:
    """Return (attendance_rows, pack_count, temp_staff_rows) for a given workday."""
    wd = d.weekday()
    is_sat = wd == 5
    present = present_fraction(d, rng)

    # Per-employee records
    att_rows: list[dict] = []
    s1_minutes = 0
    s2_minutes = 0
    for emp in employees:
        if rng.random() > present:
            continue
        # Saturday -> half shift 4-5 hr; weekday -> base ± overtime
        if is_sat:
            hours = round(rng.uniform(4.0, 5.5), 2)
            start_jitter = rng.randint(-10, 20)
        else:
            # base hours plus an OT tail: 70% no OT, 25% short OT (<1h), 5% long OT (1-2h)
            ot_roll = rng.random()
            if ot_roll < 0.70:
                ot = rng.uniform(-0.15, 0.25)
            elif ot_roll < 0.95:
                ot = rng.uniform(0.25, 0.85)
            else:
                ot = rng.uniform(0.85, 2.00)
            hours = round(emp.base_hours + ot, 2)
            start_jitter = rng.randint(-15, 15)

        start_min = max(420, min(600, emp.base_start_min + start_jitter))
        leave_min = start_min + int(round(hours * 60))

        # attendance_records schema stores commute_time (HH:MM), time_to_leave (HH:MM),
        # working_hours (free-form like "8:30 hr")
        att_rows.append({
            "personal_code": emp.code,
            "full_name": emp.name,
            "commute_time": minutes_to_hhmm(start_min),
            "time_to_leave": minutes_to_hhmm(leave_min % (24 * 60)),
            "working_hours": hours_to_working_hours_str(hours),
        })

        total_min = int(round(hours * 60))
        if emp.section == 1:
            s1_minutes += total_min
        else:
            s2_minutes += total_min

    # Target pack count: aim for Section 1 LP = 85 ± noise  →  packs ≈ 85 × s1_hours.
    # This automatically yields Section 2 LP and Combined LP in the expected band
    # because the same pack count is divided by each dept's hours independently.
    s1_hours = s1_minutes / 60.0
    intensity = day_intensity(d, rng)
    # Pick an LP_s1 sample around TARGET_S1 with intensity applied.
    lp_s1_sample = rng.gauss(TARGET_S1, 6.0) * intensity
    lp_s1_sample = max(55.0, min(115.0, lp_s1_sample))  # clamp
    packs = int(round(lp_s1_sample * s1_hours)) if s1_hours > 0 else 0

    # Temp-staff ~30% of weekdays, a single フルキャスト bucket
    temp_rows: list[dict] = []
    if not is_sat and rng.random() < 0.30:
        head = rng.choice([3, 4, 5, 6, 7])
        start_min = rng.choice([540, 570, 600])  # 9:00 / 9:30 / 10:00
        hours = round(rng.uniform(6.0, 8.5), 2)
        leave_min = start_min + int(round(hours * 60))
        temp_rows.append({
            "company": "フルキャスト",
            "headcount": head,
            "start_time": minutes_to_hhmm(start_min),
            "leave_time": minutes_to_hhmm(leave_min % (24 * 60)),
            "hours_per_person": round(hours, 2),
            "total_hours": round(hours * head, 2),
            "note": "demo",
        })

    return att_rows, packs, temp_rows


# ------------------------------------------------------------------
# Writer
# ------------------------------------------------------------------
def seed(start: date, end: date, replace: bool, dry: bool) -> None:
    employees = load_roster()
    s1_count = sum(1 for e in employees if e.section == 1)
    s2_count = sum(1 for e in employees if e.section == 2)
    print(f"Roster: {len(employees)} employees  (S1={s1_count}, S2={s2_count})")
    print(f"Range : {start}  →  {end}   ({(end - start).days + 1} days)")
    print(f"Mode  : {'REPLACE demo rows' if replace else 'INSERT only'}"
          f"{'  [DRY-RUN]' if dry else ''}")
    print()

    rng = random.Random(int(start.strftime('%Y%m%d')))
    per_day_preview: list[tuple[date, int, int, float, float, float]] = []

    all_att_rows: list[tuple] = []
    all_pack_rows: list[tuple] = []
    all_temp_rows: list[tuple] = []

    d = start
    while d <= end:
        if is_workday(d):
            att, packs, temps = gen_day(d, employees, rng)
            file_name = f"{DEMO_FILE_PREFIX}{d.isoformat()}.xlsx"
            month_year = d.strftime("%Y-%m")
            for r in att:
                all_att_rows.append((
                    file_name,
                    r["personal_code"],
                    r["full_name"],
                    r["commute_time"],
                    r["time_to_leave"],
                    r["working_hours"],
                    d,
                    month_year,
                ))
            all_pack_rows.append((d, packs, "demo"))
            for t in temps:
                all_temp_rows.append((
                    d, t["company"], t["headcount"],
                    t["start_time"], t["leave_time"],
                    t["hours_per_person"], t["total_hours"], t["note"],
                ))

            # LP preview for sanity
            s1_m = sum(_minutes(r["working_hours"]) for r in att
                       if _section_of(r["personal_code"], employees) == 1)
            s2_m = sum(_minutes(r["working_hours"]) for r in att
                       if _section_of(r["personal_code"], employees) == 2)
            s1h, s2h = s1_m / 60, s2_m / 60
            lp1 = packs / s1h if s1h else 0
            lp2 = packs / s2h if s2h else 0
            lpc = packs / (s1h + s2h) if (s1h + s2h) else 0
            per_day_preview.append((d, packs, len(att), lp1, lp2, lpc))

        d += timedelta(days=1)

    # Print a compact preview (every 7 days)
    print(f"{'Date':<12}{'DoW':<5}{'Packs':>8}{'Staff':>7}"
          f"{'LP1':>8}{'LP2':>8}{'LPc':>8}")
    for i, (dd, p, n, lp1, lp2, lpc) in enumerate(per_day_preview):
        if i % 7 == 0 or i == len(per_day_preview) - 1:
            dow = "月火水木金土日"[dd.weekday()]
            print(f"{dd.isoformat():<12}{dow:<5}{p:>8}{n:>7}"
                  f"{lp1:>8.1f}{lp2:>8.1f}{lpc:>8.1f}")

    # Aggregate sanity
    if per_day_preview:
        tot_p = sum(x[1] for x in per_day_preview)
        avg_lp1 = sum(x[3] for x in per_day_preview) / len(per_day_preview)
        avg_lp2 = sum(x[4] for x in per_day_preview) / len(per_day_preview)
        avg_lpc = sum(x[5] for x in per_day_preview) / len(per_day_preview)
        print()
        print(f"Totals: {len(per_day_preview)} workdays, {tot_p:,} packs total")
        print(f"Avg LP: S1={avg_lp1:.1f}  S2={avg_lp2:.1f}  Combined={avg_lpc:.1f}")
        print(f"Target: S1={TARGET_S1}  S2={TARGET_S2}  Combined={TARGET_COMBINED}")

    if dry:
        print("\nDRY-RUN: no DB writes. Re-run without --dry-run to commit.")
        return

    print("\nWriting to DB...")
    with psycopg2.connect(**DB) as conn:
        with conn.cursor() as cur:
            if replace:
                cur.execute(
                    "DELETE FROM attendance_records "
                    "WHERE record_date BETWEEN %s AND %s "
                    "AND file_name LIKE %s",
                    (start, end, f"{DEMO_FILE_PREFIX}%"))
                cur.execute(
                    "DELETE FROM daily_packs "
                    "WHERE record_date BETWEEN %s AND %s "
                    "AND note = 'demo'",
                    (start, end))
                cur.execute(
                    "DELETE FROM temp_staff "
                    "WHERE record_date BETWEEN %s AND %s AND note = 'demo'",
                    (start, end))
                print(f"  deleted existing demo rows in window")

            # attendance_records
            cur.executemany(
                """INSERT INTO attendance_records
                   (file_name, personal_code, full_name,
                    commute_time, time_to_leave, working_hours,
                    record_date, month_year)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                all_att_rows,
            )
            print(f"  attendance_records: {len(all_att_rows):,} rows inserted")

            # daily_packs (upsert so re-runs without --replace are safe)
            cur.executemany(
                """INSERT INTO daily_packs (record_date, number_of_packs, note)
                   VALUES (%s,%s,%s)
                   ON CONFLICT (record_date) DO UPDATE
                     SET number_of_packs = EXCLUDED.number_of_packs,
                         note = EXCLUDED.note,
                         updated_at = NOW()""",
                all_pack_rows,
            )
            print(f"  daily_packs      : {len(all_pack_rows):,} rows upserted")

            # temp_staff
            if all_temp_rows:
                cur.executemany(
                    """INSERT INTO temp_staff
                       (record_date, company, headcount, start_time, leave_time,
                        hours_per_person, total_hours, note)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    all_temp_rows,
                )
                print(f"  temp_staff       : {len(all_temp_rows):,} rows inserted")

            # a single upload_batches header for traceability
            cur.execute(
                """INSERT INTO upload_batches (file_name, total_records)
                   VALUES (%s, %s)""",
                (f"{DEMO_FILE_PREFIX}{start}_to_{end}.xlsx", len(all_att_rows)),
            )
        conn.commit()
    print("Done.")


# ------------------------------------------------------------------
# Small helpers
# ------------------------------------------------------------------
_SECTION_CACHE: dict[str, int] = {}

def _section_of(code: str, employees: list[Employee]) -> int:
    if not _SECTION_CACHE:
        for e in employees:
            _SECTION_CACHE[e.code] = e.section
    return _SECTION_CACHE.get(code, 0)


def _minutes(wh: str) -> int:
    # "8:30 hr" -> 510
    s = wh.replace("hr", "").strip()
    if ":" not in s:
        return 0
    h, m = s.split(":", 1)
    try:
        return int(h) * 60 + int(m)
    except ValueError:
        return 0


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------
def main() -> None:
    today = datetime.now().date()
    parser = argparse.ArgumentParser(description="Seed 3 months of demo data.")
    parser.add_argument("--start", help="YYYY-MM-DD, inclusive", default=None)
    parser.add_argument("--end", help="YYYY-MM-DD, inclusive", default=None)
    parser.add_argument("--days", type=int, default=92,
                        help="If --start/--end not given, seed this many days ending today")
    parser.add_argument("--replace", action="store_true",
                        help="Delete existing DEMO-SEED rows in the window before inserting")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show preview and totals, do not write to DB")
    args = parser.parse_args()

    if args.start:
        start = datetime.strptime(args.start, "%Y-%m-%d").date()
    else:
        start = today - timedelta(days=args.days - 1)
    if args.end:
        end = datetime.strptime(args.end, "%Y-%m-%d").date()
    else:
        end = today

    if start > end:
        parser.error("start must be <= end")

    seed(start, end, replace=args.replace, dry=args.dry_run)


if __name__ == "__main__":
    main()
