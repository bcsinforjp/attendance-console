"""
date_service.py
================
Central source of truth for EVERY date calculation in the attendance app.

If you ever need to change a date rule (e.g. shift becomes production - 2
instead of -1), edit it HERE — nowhere else.

Plain-language guide (worked examples, function reference, pitfalls):
    DATE_RULES.md  (same folder)

------------------------------------------------------------------------
THE FIVE DATE CONCEPTS
------------------------------------------------------------------------
  1. PDF date         勤怠PDF日       day printed on the attendance PDF
  2. Shift date       シフト日        day the worker was on shift
                                      (also = フルキャスト / temp_staff /
                                       part-time / employee record_date)
  3. Production date  生産日          day packs are booked to in Excel
  4. Report date      レポート日      day shown on dashboards / LINE cards
  5. Pack date        パック日        alias of production_date

------------------------------------------------------------------------
THE GOLDEN RULES  (edit offsets in CONFIG below — that's the only place)
------------------------------------------------------------------------

      pdf_date  ──+1──▶  production_date  ──-1──▶  shift_date
                               ║
                               ╠═══════════ report_date  (same day)
                               ╚═══════════ pack_date    (same day)

  So:
      report_date  =  production_date  =  pdf_date + 1
      shift_date   =  production_date - 1
      employee record_date  = shift_date
      temp_staff record_date = shift_date
      daily_packs record_date = production_date

------------------------------------------------------------------------
USAGE  (in main.py)
------------------------------------------------------------------------
    from date_service import (
        pdf_to_production, production_to_shift, report_to_shift,
        parse_iso, to_iso, month_year, excel_serial_to_date,
        date_from_filename, window, date_axis, now_iso, yesterday,
    )

    prod = pdf_to_production("2026-05-02")      # date(2026, 5, 3)
    shift = production_to_shift(prod)            # date(2026, 5, 2)
    iso = to_iso(prod)                           # "2026-05-03"
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta


# ════════════════════════════════════════════════════════════════════════
# CONFIG — the only place to edit when date rules change
# ════════════════════════════════════════════════════════════════════════

# Offsets between the five concepts (in days).
PDF_TO_PRODUCTION_DAYS = 1       # production = pdf + 1
PRODUCTION_TO_SHIFT_DAYS = -1    # shift = production - 1
REPORT_TO_PRODUCTION_DAYS = 0    # report = production (alias)
PACK_TO_PRODUCTION_DAYS = 0      # pack   = production (alias)

# Excel serial-number epoch. 1899-12-30 (not 1900-01-01) compensates for
# Excel's 1900-leap-year bug.
EXCEL_EPOCH = datetime(1899, 12, 30)

# Date-string formats used across the app.
ISO_DATE = "%Y-%m-%d"
ISO_MONTH = "%Y-%m"
JP_DATE = "%Y年%m月%d日"
FILENAME_TS = "%Y%m%d_%H%M%S"

# Regex for extracting a date out of a filename.
# Accepts 2026-04-29, 26.04.29, 26_04_29, 2026/04/29, etc.
_FILENAME_DATE_RE = re.compile(r"(\d{2,4})[._\-/](\d{1,2})[._\-/](\d{1,2})")
_FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")


# ════════════════════════════════════════════════════════════════════════
# INTERNAL — input normalization
# ════════════════════════════════════════════════════════════════════════

def _to_date(value) -> date:
    """Coerce str | date | datetime → date. Single funnel for all inputs."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return datetime.strptime(value.strip(), ISO_DATE).date()
    raise TypeError(f"date_service: unsupported date input: {type(value)!r}")


# ════════════════════════════════════════════════════════════════════════
# CORE CONVERSIONS — replace every scattered timedelta in main.py
# ════════════════════════════════════════════════════════════════════════

def pdf_to_production(d) -> date:
    """勤怠PDF日 → 生産日 (= report = pack)."""
    return _to_date(d) + timedelta(days=PDF_TO_PRODUCTION_DAYS)


def production_to_pdf(d) -> date:
    """生産日 → 勤怠PDF日."""
    return _to_date(d) - timedelta(days=PDF_TO_PRODUCTION_DAYS)


def production_to_shift(d) -> date:
    """生産日 → シフト日  (= temp_staff / employee record_date)."""
    return _to_date(d) + timedelta(days=PRODUCTION_TO_SHIFT_DAYS)


def shift_to_production(d) -> date:
    """シフト日 → 生産日."""
    return _to_date(d) - timedelta(days=PRODUCTION_TO_SHIFT_DAYS)


def report_to_production(d) -> date:
    """レポート日 → 生産日 (alias, no offset)."""
    return _to_date(d) + timedelta(days=REPORT_TO_PRODUCTION_DAYS)


def production_to_report(d) -> date:
    return _to_date(d) - timedelta(days=REPORT_TO_PRODUCTION_DAYS)


def pack_to_production(d) -> date:
    """パック日 → 生産日 (alias, no offset)."""
    return _to_date(d) + timedelta(days=PACK_TO_PRODUCTION_DAYS)


def production_to_pack(d) -> date:
    return _to_date(d) - timedelta(days=PACK_TO_PRODUCTION_DAYS)


# ──────────────── Convenience chains used by API endpoints ────────────────

def report_to_shift(d) -> date:
    """レポート日 → シフト日  (used by /api/temp-staff and gantt queries)."""
    return production_to_shift(report_to_production(d))


def report_to_pdf(d) -> date:
    """レポート日 → 勤怠PDF日."""
    return production_to_pdf(report_to_production(d))


def pdf_to_shift(d) -> date:
    """勤怠PDF日 → シフト日."""
    return production_to_shift(pdf_to_production(d))


# ──────────────── Table-key helpers (self-documenting names) ──────────────

def employee_record_date(production_date) -> date:
    """attendance_records.record_date for a given production day."""
    return production_to_shift(production_date)


def temp_staff_record_date(production_date) -> date:
    """temp_staff.record_date (フルキャスト / part-time) for a production day."""
    return production_to_shift(production_date)


def pack_record_date(production_date) -> date:
    """daily_packs.record_date / daily_pack_items.production_date."""
    return _to_date(production_date)


# ════════════════════════════════════════════════════════════════════════
# PARSING & FORMATTING
# ════════════════════════════════════════════════════════════════════════

def parse_iso(s: str) -> date:
    """'YYYY-MM-DD' → date. Raises ValueError on bad input."""
    return datetime.strptime(s.strip(), ISO_DATE).date()


def parse_flexible(s: str) -> date:
    """Try YYYY-MM-DD, YYYY/MM/DD, DD/MM/YYYY, DD-MM-YYYY in that order."""
    s = s.strip()
    for fmt in (ISO_DATE, "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"date_service: unrecognised date {s!r}")


def to_iso(d) -> str:
    """date → 'YYYY-MM-DD'."""
    return _to_date(d).isoformat()


def to_japanese(d) -> str:
    """date → 'YYYY年MM月DD日'."""
    return _to_date(d).strftime(JP_DATE)


def month_year(d) -> str:
    """date → 'YYYY-MM' (the month_year column of attendance_records)."""
    return _to_date(d).strftime(ISO_MONTH)


def first_of_month(month_str: str) -> date:
    """'YYYY-MM' → date(YYYY, MM, 1)."""
    return datetime.strptime(f"{month_str}-01", ISO_DATE).date()


# ════════════════════════════════════════════════════════════════════════
# RANGES & WINDOWS  (gantt, members-compare, mobile-summary)
# ════════════════════════════════════════════════════════════════════════

def date_axis(start, end) -> list[str]:
    """Inclusive list of 'YYYY-MM-DD' strings from start to end."""
    s, e = _to_date(start), _to_date(end)
    span = (e - s).days + 1
    return [(s + timedelta(days=i)).isoformat() for i in range(span)]


def window(anchor, days: int) -> tuple[date, date]:
    """Trailing N-day window ending at anchor (inclusive). Returns (start, end)."""
    a = _to_date(anchor)
    return (a - timedelta(days=days - 1), a)


def previous_window(start, end) -> tuple[date, date]:
    """The window immediately before (start, end), same length."""
    s, e = _to_date(start), _to_date(end)
    n = (e - s).days + 1
    prev_end = s - timedelta(days=1)
    return (prev_end - timedelta(days=n - 1), prev_end)


def add_days(d, n: int) -> date:
    """Generic offset, used for cleanup cutoffs etc."""
    return _to_date(d) + timedelta(days=n)


# ════════════════════════════════════════════════════════════════════════
# EXCEL & FILENAMES
# ════════════════════════════════════════════════════════════════════════

def excel_serial_to_date(serial) -> date:
    """Excel serial number → date. Handles the 1900-leap-year bug."""
    return (EXCEL_EPOCH + timedelta(days=int(serial))).date()


def date_from_filename(name: str) -> date | None:
    """Extract a date from a filename. None if no recognisable date is present.

    Accepts ASCII and full-width digits, 2- or 4-digit years, separators
    `.`, `-`, `_`, `/`. 2-digit years are treated as 2000s.
    """
    m = _FILENAME_DATE_RE.search(name.translate(_FULLWIDTH_DIGITS))
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    if y < 100:
        y += 2000
    try:
        return date(y, mo, d)
    except ValueError:
        return None


# ════════════════════════════════════════════════════════════════════════
# TIMESTAMPS  (audit / metadata only — NOT business dates)
# ════════════════════════════════════════════════════════════════════════

def now_iso() -> str:
    """Server-local 'YYYY-MM-DDTHH:MM:SS' for saved_at / updated_at fields."""
    return datetime.now().isoformat(timespec="seconds")


def utc_iso_z() -> str:
    """UTC 'YYYY-MM-DDTHH:MM:SSZ' for API responses."""
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def filename_stamp() -> str:
    """'20260503_142318' for unique filenames."""
    return datetime.now().strftime(FILENAME_TS)


# ════════════════════════════════════════════════════════════════════════
# DEFAULTS
# ════════════════════════════════════════════════════════════════════════

def today() -> date:
    return date.today()


def yesterday() -> date:
    """Default report / production date when none is supplied."""
    return date.today() - timedelta(days=1)


# ════════════════════════════════════════════════════════════════════════
# Self-check  —  run `python date_service.py` to verify the rules
# ════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pdf = date(2026, 5, 2)
    prod = pdf_to_production(pdf)
    shift = production_to_shift(prod)

    print("date_service self-check")
    print("-----------------------")
    print(f"PDF date         : {pdf}")
    print(f"Production date  : {prod}   (= report = pack)")
    print(f"Shift date       : {shift}  (= temp_staff / employee record_date)")
    print()
    print(f"Round-trip pdf↔prod   : {production_to_pdf(prod) == pdf}")
    print(f"Round-trip prod↔shift : {shift_to_production(shift) == prod}")
    print(f"report_to_shift(prod) : {report_to_shift(prod)}  (expected {shift})")
    print()
    print(f"Excel serial 45000    : {excel_serial_to_date(45000)}")
    print(f"date_from_filename    : {date_from_filename('attendance_2026-05-02.pdf')}")
    print(f"month_year(prod)      : {month_year(prod)}")
    print(f"window(prod, 7)       : {window(prod, 7)}")
