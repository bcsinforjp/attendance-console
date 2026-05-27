"""
partner_api.py — external company-to-company data API (separate module).

Decoupled from main.py (could become a standalone service unchanged).

  * Deny-by-default: OFF until an admin enables it AND a partner token exists.
  * Per-partner bearer tokens — revocable, rate-limited, optional IP allowlist,
    optional monthly quota.
  * Curated READ-ONLY data, fetched from the app's own trusted internal
    endpoints over localhost (never raw SQL / never users/keys/config).
  * Consistent response envelope + machine error codes.
  * ETag / Cache-Control on read endpoints (304 on If-None-Match).
  * Per-partner usage analytics (today / month) + monthly quota.
  * OpenAPI 3.0 spec + Swagger UI.
  * Every call logged to partner_api_requests.jsonl.

main.py does:
    from partner_api import router, register_partner_error_handler, ...
    app.include_router(router); register_partner_error_handler(app)
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, HTMLResponse, PlainTextResponse

BASE_DIR = Path(__file__).resolve().parent
PARTNER_CONFIG_PATH = BASE_DIR / "partner_api.json"
PARTNER_USAGE_PATH = BASE_DIR / "partner_usage.json"

_LOG_DIR = Path(os.environ.get("AI_SERVER_LOG_DIR", "/var/log/ai_server"))
try:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
except PermissionError:
    _LOG_DIR = BASE_DIR / "logs"
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
PARTNER_LOG_PATH = _LOG_DIR / "partner_api_requests.jsonl"

SELF_BASE = f"http://127.0.0.1:{os.environ.get('ATTENDANCE_SELF_PORT', '8002')}"
API_VERSION = "1.1"

router = APIRouter(prefix="/partner/v1", tags=["partner-api"])


# ---- error type (enveloped, machine codes) --------------------------------
class PartnerAPIError(Exception):
    def __init__(self, status: int, code: str, message: str, headers: dict | None = None):
        self.status = status
        self.code = code
        self.message = message
        self.headers = headers or {}
        super().__init__(message)


def register_partner_error_handler(app) -> None:
    """Scoped error envelope — only fires for PartnerAPIError (partner code),
    so the rest of the app's error shape is untouched."""
    @app.exception_handler(PartnerAPIError)
    async def _handle(request: Request, exc: PartnerAPIError):
        try:
            _log("?", "?", _client_ip(request), request.url.path, exc.status, 0)
        except Exception:
            pass
        return JSONResponse(
            status_code=exc.status,
            content={"ok": False, "error": {"code": exc.code, "message": exc.message}},
            headers=exc.headers,
        )


# ---- config helpers --------------------------------------------------------
def _load() -> dict:
    try:
        if PARTNER_CONFIG_PATH.exists():
            d = json.loads(PARTNER_CONFIG_PATH.read_text(encoding="utf-8"))
            d.setdefault("enabled", False)
            d.setdefault("partners", [])
            return d
    except Exception as exc:
        print(f"[PARTNER_API] config read failed: {exc}")
    return {"enabled": False, "partners": []}


def _save(cfg: dict) -> None:
    tmp = PARTNER_CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(PARTNER_CONFIG_PATH)
    try:
        os.chmod(PARTNER_CONFIG_PATH, 0o600)
    except Exception:
        pass


_RT: dict = {}      # pid -> [window_start_epoch, count]
_STAT: dict = {}    # pid -> {calls,last_seen,last_ip}


# ---- usage analytics (persistent, lazy flush) ------------------------------
_usage_lock = threading.Lock()
_USAGE: dict = {}                 # pid -> {"YYYY-MM-DD": int}
_usage_last_save = 0.0
try:
    if PARTNER_USAGE_PATH.exists():
        _USAGE = json.loads(PARTNER_USAGE_PATH.read_text(encoding="utf-8")) or {}
except Exception:
    _USAGE = {}


def _usage_flush(force: bool = False) -> None:
    global _usage_last_save
    now = time.time()
    if not force and (now - _usage_last_save) < 20:
        return
    _usage_last_save = now
    try:
        tmp = PARTNER_USAGE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(_USAGE, ensure_ascii=False), encoding="utf-8")
        tmp.replace(PARTNER_USAGE_PATH)
    except Exception as exc:
        print(f"[PARTNER_API] usage flush failed: {exc}")


def _usage_counts(pid: str):
    today = datetime.now().strftime("%Y-%m-%d")
    ym = today[:7]
    with _usage_lock:
        days = _USAGE.get(pid, {})
        return days.get(today, 0), sum(v for k, v in days.items() if k.startswith(ym))


def _usage_bump(pid: str) -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    with _usage_lock:
        d = _USAGE.setdefault(pid, {})
        d[today] = d.get(today, 0) + 1
        # keep ~120 most recent days per partner
        if len(d) > 130:
            for k in sorted(d)[:-120]:
                d.pop(k, None)
    _usage_flush()


def _client_ip(request: Request) -> str:
    return (
        request.headers.get("x-real-ip")
        or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "?")
    )


def _log(partner_id: str, name: str, ip: str, path: str, status: int, ms: int) -> None:
    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "partner_id": partner_id, "partner": name, "ip": ip,
        "path": path, "status": status, "duration_ms": ms,
    }
    try:
        with PARTNER_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if PARTNER_LOG_PATH.stat().st_size > 5 * 1024 * 1024:
            lines = PARTNER_LOG_PATH.read_text(encoding="utf-8").splitlines()[-4000:]
            PARTNER_LOG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception as exc:
        print(f"[PARTNER_API] log write failed: {exc}")


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("x-partner-token") or None


def _require_partner(request: Request) -> dict:
    """Auth + abuse + quota gate. Raises PartnerAPIError; returns the partner."""
    cfg = _load()
    if not cfg.get("enabled"):
        raise PartnerAPIError(503, "api_disabled", "Partner API is disabled.")
    token = _extract_token(request)
    if not token:
        raise PartnerAPIError(401, "missing_token",
                              "Provide Authorization: Bearer <token>.")
    partner = None
    for p in cfg.get("partners", []):
        if secrets.compare_digest(str(p.get("token", "")), token):
            partner = p
            break
    if partner is None:
        raise PartnerAPIError(401, "invalid_token", "Invalid partner token.")
    if partner.get("disabled"):
        raise PartnerAPIError(403, "partner_disabled", "This partner is disabled.")
    ip = _client_ip(request)
    allow = partner.get("ip_allowlist") or []
    if allow and ip not in allow:
        raise PartnerAPIError(403, "ip_not_allowed",
                              "Source IP not allowed for this partner.")
    pid = partner["id"]
    # Per-partner fixed-window rate limit.
    rpm = int(partner.get("rate_per_min", 60) or 60)
    now = time.time()
    win = _RT.get(pid)
    if not win or (now - win[0]) >= 60:
        _RT[pid] = [now, 0]
        win = _RT[pid]
    win[1] += 1
    if win[1] > rpm:
        retry = max(1, int(60 - (now - win[0])))
        raise PartnerAPIError(429, "rate_limited",
                              f"Rate limit exceeded ({rpm}/min).",
                              {"Retry-After": str(retry)})
    # Monthly quota (0/None = unlimited).
    quota = int(partner.get("monthly_quota", 0) or 0)
    if quota > 0:
        _, month = _usage_counts(pid)
        if month + 1 > quota:
            raise PartnerAPIError(429, "quota_exceeded",
                                  f"Monthly quota exhausted ({quota}/month).",
                                  {"Retry-After": "3600"})
    _usage_bump(pid)
    st = _STAT.setdefault(pid, {"calls": 0})
    st["calls"] += 1
    st["last_seen"] = datetime.now().isoformat(timespec="seconds")
    st["last_ip"] = ip
    return partner


def _proxy_json(path: str):
    """GET a trusted internal endpoint over localhost; return parsed JSON."""
    url = SELF_BASE + path
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise PartnerAPIError(502, "upstream_unavailable",
                              f"Upstream data unavailable: {exc}")


def _paginate(data, limit: int | None, offset: int):
    """If `data` (or data['items']) is a list, apply limit/offset and report
    pagination meta. Objects pass through untouched."""
    meta = {}
    target_key = None
    seq = None
    if isinstance(data, list):
        seq = data
    elif isinstance(data, dict) and isinstance(data.get("items"), list):
        seq, target_key = data["items"], "items"
    if seq is None:
        return data, meta
    total = len(seq)
    off = max(0, int(offset or 0))
    lim = total if (limit in (None, 0)) else max(1, min(int(limit), 1000))
    page = seq[off:off + lim]
    meta = {"total": total, "offset": off, "limit": lim, "returned": len(page)}
    if target_key:
        out = dict(data)
        out[target_key] = page
        return out, meta
    return page, meta


def _envelope(request: Request, partner: dict, data, *,
              extra_meta: dict | None = None, max_age: int = 60,
              status: int = 200) -> Response:
    """Build the consistent envelope with ETag/Cache-Control + 304 support."""
    meta = {
        "partner": partner.get("name"),
        "ts": datetime.now().isoformat(timespec="seconds"),
        "api_version": API_VERSION,
        "cached": False,
    }
    if extra_meta:
        meta.update(extra_meta)
    body = {"ok": True, "data": data, "meta": meta}
    raw = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
    etag = 'W/"%s"' % hashlib.sha1(raw).hexdigest()[:20]
    ms = int((time.time() - getattr(request.state, "_t0", time.time())) * 1000)
    inm = request.headers.get("if-none-match", "")
    if max_age > 0 and inm and etag in [t.strip() for t in inm.split(",")]:
        _log(partner["id"], partner.get("name", "?"), _client_ip(request),
             request.url.path, 304, ms)
        return Response(status_code=304, headers={
            "ETag": etag,
            "Cache-Control": f"private, max-age={max_age}",
        })
    cc = f"private, max-age={max_age}" if max_age > 0 else "no-store"
    _log(partner["id"], partner.get("name", "?"), _client_ip(request),
         request.url.path, status, ms)
    return JSONResponse(status_code=status, content=body,
                        headers={"ETag": etag, "Cache-Control": cc})


# ---- read-only data endpoints ---------------------------------------------
@router.get("/ping")
def partner_ping(request: Request):
    request.state._t0 = time.time()
    p = _require_partner(request)
    return _envelope(request, p, {
        "pong": True,
        "server_time": datetime.now().isoformat(timespec="seconds"),
    }, max_age=0)


@router.get("/datasets")
def partner_datasets(request: Request, limit: int | None = None, offset: int = 0):
    request.state._t0 = time.time()
    p = _require_partner(request)
    sets = [
        {"path": "/v1/production?date=YYYY-MM-DD",
         "desc": "daily production + section/productivity summary for a date"},
        {"path": "/v1/productivity?range=month&end=YYYY-MM-DD",
         "desc": "labor productivity series + summary (range: day|week|month|3month)"},
        {"path": "/v1/packs?date=YYYY-MM-DD",
         "desc": "per-item produced-packs rows for a date"},
        {"path": "/v1/attendance?date=YYYY-MM-DD",
         "desc": "per-employee attendance: name, in/out, worked hours + per-section & grand totals"},
    ]
    page, pm = _paginate(sets, limit, offset)
    return _envelope(request, p, page, extra_meta=pm, max_age=600)


@router.get("/production")
def partner_production(request: Request, date: str | None = None):
    request.state._t0 = time.time()
    p = _require_partner(request)
    snap = _proxy_json("/api/dashboard/snapshot" + (f"?date={date}" if date else ""))
    out = {
        "report_date": snap.get("report_date"),
        "today": snap.get("today"),
        "productivity": snap.get("productivity"),
        "plan": snap.get("plan"),
    }
    return _envelope(request, p, out, max_age=60)


@router.get("/productivity")
def partner_productivity(request: Request, range: str = "month", end: str | None = None):
    request.state._t0 = time.time()
    p = _require_partner(request)
    q = f"?range={range}" + (f"&end={end}" if end else "")
    data = _proxy_json("/api/productivity" + q)
    return _envelope(request, p, data, max_age=60)


@router.get("/packs")
def partner_packs(request: Request, date: str,
                  limit: int | None = None, offset: int = 0):
    request.state._t0 = time.time()
    p = _require_partner(request)
    data = _proxy_json(f"/api/daily-packs/items/{date}")
    page, pm = _paginate(data, limit, offset)
    return _envelope(request, p, page, extra_meta=pm, max_age=60)


def _hhmm_to_min(v) -> int:
    if not v:
        return 0
    s = str(v).strip()
    try:
        if ":" in s:
            h, m = s.split(":")[:2]
            return int(h) * 60 + int(m)
        return int(round(float(s) * 60))
    except Exception:
        return 0


def _min_to_hhmm(t: int) -> str:
    t = max(0, int(t))
    return f"{t // 60}:{t % 60:02d}"


@router.get("/attendance")
def partner_attendance(request: Request, date: str,
                       section: int | None = None,
                       limit: int | None = None, offset: int = 0):
    """Per-employee attendance for a date: names, in/out, worked hours,
    plus per-section and grand totals. `section` (1|2) optional filter."""
    request.state._t0 = time.time()
    p = _require_partner(request)
    g = _proxy_json(f"/api/gantt/{date}")
    employees = []
    by_section = []
    for s in (g.get("sections") or []):
        if section and s.get("id") != section:
            continue
        rows = s.get("rows") or []
        s_min = 0
        s_present = 0
        for r in rows:
            mins = _hhmm_to_min(r.get("wh"))
            if mins > 0:
                s_present += 1
            s_min += mins
            employees.append({
                "name": r.get("name"),
                "code": r.get("code"),
                "section_id": s.get("id"),
                "section": s.get("label"),
                "in": r.get("in"),
                "out": r.get("out"),
                "hours": r.get("wh"),
                "minutes": mins,
                "is_temp": bool(r.get("is_temp")),
            })
        by_section.append({
            "id": s.get("id"), "label": s.get("label"),
            "employees": len(rows), "present": s_present,
            "total_hours_hhmm": _min_to_hhmm(s_min),
            "total_hours": round(s_min / 60.0, 2),
        })
    grand = sum(e["minutes"] for e in employees)
    totals = {
        "employees": len(employees),
        "present": sum(1 for e in employees if e["minutes"] > 0),
        "total_hours_hhmm": _min_to_hhmm(grand),
        "total_hours": round(grand / 60.0, 2),
        "by_section": by_section,
    }
    page, pm = _paginate(employees, limit, offset)
    out = {"date": g.get("date"), "employees": page, "totals": totals}
    return _envelope(request, p, out, extra_meta=pm, max_age=60)


# ---- OpenAPI 3.0 + Swagger UI ---------------------------------------------
def _openapi_spec() -> dict:
    # ---- reusable components -----------------------------------------------
    schemas = {
        "Meta": {
            "type": "object",
            "description": "Response metadata. Pagination keys appear only on list responses.",
            "properties": {
                "partner":     {"type": "string", "description": "Calling partner name", "example": "ACME Co"},
                "ts":          {"type": "string", "format": "date-time",
                                "description": "Server timestamp (ISO 8601)"},
                "api_version": {"type": "string", "example": API_VERSION},
                "cached":      {"type": "boolean", "description": "Reserved for future cache hints", "example": False},
                "total":       {"type": "integer", "description": "Total items (list responses only)"},
                "offset":      {"type": "integer"},
                "limit":       {"type": "integer"},
                "returned":    {"type": "integer", "description": "Items in this page"},
            },
        },
        "Envelope": {
            "type": "object",
            "required": ["ok", "data", "meta"],
            "properties": {
                "ok":   {"type": "boolean", "example": True},
                "data": {"description": "Endpoint-specific payload (see typed schemas)"},
                "meta": {"$ref": "#/components/schemas/Meta"},
            },
        },
        "ErrorEnvelope": {
            "type": "object",
            "required": ["ok", "error"],
            "properties": {
                "ok": {"type": "boolean", "example": False},
                "error": {
                    "type": "object",
                    "required": ["code", "message"],
                    "properties": {
                        "code": {"type": "string",
                                 "enum": ["missing_token", "invalid_token",
                                          "partner_disabled", "ip_not_allowed",
                                          "rate_limited", "quota_exceeded",
                                          "api_disabled", "upstream_unavailable"]},
                        "message": {"type": "string"},
                    },
                },
            },
            "example": {"ok": False, "error":
                        {"code": "missing_token",
                         "message": "Provide Authorization: Bearer <token>."}},
        },
        "Dataset": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "example": "/v1/production?date=YYYY-MM-DD"},
                "desc": {"type": "string"},
            },
        },
        "ProductivitySummary": {
            "type": "object",
            "properties": {
                "total_packs":          {"type": "integer"},
                "total_hours_s1":       {"type": "number"},
                "total_hours_s2":       {"type": "number"},
                "total_hours_combined": {"type": "number"},
                "lp_s1":                {"type": "number", "description": "Packs/hour, Section 1 (target 85)"},
                "lp_s2":                {"type": "number", "description": "Packs/hour, Section 2 (target 35)"},
                "lp_combined":          {"type": "number", "description": "Packs/hour, combined (target 25)"},
            },
        },
        "ProductivityPeriod": {
            "type": "object",
            "properties": {
                "start": {"type": "string", "format": "date"},
                "end":   {"type": "string", "format": "date"},
                "summary": {"$ref": "#/components/schemas/ProductivitySummary"},
                "series": {
                    "type": "object",
                    "description": "Parallel arrays indexed by `labels`",
                    "properties": {
                        "labels":      {"type": "array", "items": {"type": "string", "format": "date"}},
                        "lp_s1":       {"type": "array", "items": {"type": "number"}},
                        "lp_s2":       {"type": "array", "items": {"type": "number"}},
                        "lp_combined": {"type": "array", "items": {"type": "number"}},
                        "packs":       {"type": "array", "items": {"type": "integer"}},
                    },
                },
            },
        },
        "ProductivityData": {
            "type": "object",
            "properties": {
                "range":    {"type": "string", "enum": ["day", "week", "month", "3month"]},
                "current":  {"$ref": "#/components/schemas/ProductivityPeriod"},
                "previous": {"$ref": "#/components/schemas/ProductivityPeriod"},
            },
        },
        "ProductionSection": {
            "type": "object",
            "properties": {
                "id":               {"type": "integer", "example": 1},
                "label":            {"type": "string", "example": "製造１課"},
                "lp":               {"type": "number"},
                "staff_present":    {"type": "integer"},
                "staff_total":      {"type": "integer"},
                "total_hours_hhmm": {"type": "string", "example": "145:05"},
            },
        },
        "ProductionData": {
            "type": "object",
            "properties": {
                "report_date": {"type": "string", "format": "date"},
                "today":       {"type": "object",
                                "description": "Today's totals (packs, plan progress …)"},
                "productivity": {
                    "type": "object",
                    "properties": {"sections":
                                   {"type": "array",
                                    "items": {"$ref": "#/components/schemas/ProductionSection"}}},
                },
                "plan":        {"type": "object",
                                "description": "Today's production plan (line / item rows)"},
            },
        },
        "Employee": {
            "type": "object",
            "properties": {
                "name":       {"type": "string", "example": "山田 太郎"},
                "code":       {"type": "string", "example": "00007001"},
                "section_id": {"type": "integer", "example": 1},
                "section":    {"type": "string", "example": "製造１課"},
                "in":         {"type": "string", "nullable": True, "example": "10:44"},
                "out":        {"type": "string", "nullable": True, "example": "19:17"},
                "hours":      {"type": "string", "nullable": True,
                               "description": "Worked hours HH:MM", "example": "8:33"},
                "minutes":    {"type": "integer", "example": 513},
                "is_temp":    {"type": "boolean"},
            },
        },
        "BySection": {
            "type": "object",
            "properties": {
                "id":               {"type": "integer"},
                "label":            {"type": "string"},
                "employees":        {"type": "integer"},
                "present":          {"type": "integer"},
                "total_hours_hhmm": {"type": "string"},
                "total_hours":      {"type": "number"},
            },
        },
        "Totals": {
            "type": "object",
            "properties": {
                "employees":        {"type": "integer"},
                "present":          {"type": "integer"},
                "total_hours_hhmm": {"type": "string", "example": "674:20"},
                "total_hours":      {"type": "number", "example": 674.33},
                "by_section":       {"type": "array",
                                     "items": {"$ref": "#/components/schemas/BySection"}},
            },
        },
        "AttendanceData": {
            "type": "object",
            "properties": {
                "date":      {"type": "string", "format": "date"},
                "employees": {"type": "array",
                              "items": {"$ref": "#/components/schemas/Employee"}},
                "totals":    {"$ref": "#/components/schemas/Totals"},
            },
        },
    }

    # Envelope-of-X typed responses (data field narrowed per endpoint).
    def _typed_envelope(ref):
        return {"allOf": [
            {"$ref": "#/components/schemas/Envelope"},
            {"type": "object", "properties": {"data": {"$ref": ref}}},
        ]}
    schemas["PingEnvelope"]         = {"allOf": [{"$ref": "#/components/schemas/Envelope"},
                                                  {"type": "object", "properties": {"data": {
                                                      "type": "object",
                                                      "properties": {
                                                          "pong": {"type": "boolean", "example": True},
                                                          "server_time": {"type": "string", "format": "date-time"}}}}}]}
    schemas["DatasetsEnvelope"]     = {"allOf": [{"$ref": "#/components/schemas/Envelope"},
                                                  {"type": "object", "properties": {"data": {
                                                      "type": "array",
                                                      "items": {"$ref": "#/components/schemas/Dataset"}}}}]}
    schemas["ProductionEnvelope"]   = _typed_envelope("#/components/schemas/ProductionData")
    schemas["ProductivityEnvelope"] = _typed_envelope("#/components/schemas/ProductivityData")
    schemas["AttendanceEnvelope"]   = _typed_envelope("#/components/schemas/AttendanceData")

    headers = {
        "ETag":          {"description": "Weak ETag of the response body. Use with If-None-Match.",
                          "schema": {"type": "string", "example": 'W/"a2de6634017f2563b157"'}},
        "Cache-Control": {"description": "Caching policy for this response.",
                          "schema": {"type": "string", "example": "private, max-age=60"}},
        "Retry-After":   {"description": "Seconds the client should wait before retrying (sent on 429).",
                          "schema": {"type": "integer", "example": 60}},
    }

    def _err_resp(desc):
        return {"description": desc,
                "content": {"application/json": {"schema":
                            {"$ref": "#/components/schemas/ErrorEnvelope"}}}}
    responses = {
        "Unauthorized":       _err_resp("Missing or invalid bearer token."),
        "Forbidden":          _err_resp("Partner disabled or source IP not allowed."),
        "RateLimited":        {"description": "Rate limit or monthly quota exceeded.",
                               "headers": {"Retry-After": {"$ref": "#/components/headers/Retry-After"}},
                               "content": {"application/json":
                                           {"schema": {"$ref": "#/components/schemas/ErrorEnvelope"}}}},
        "ServiceUnavailable": _err_resp("Partner API globally disabled by admin."),
        "BadGateway":         _err_resp("Upstream data source temporarily unavailable."),
        "NotModified":        {"description": "Response matches the client's If-None-Match — body omitted.",
                               "headers": {"ETag": {"$ref": "#/components/headers/ETag"},
                                           "Cache-Control": {"$ref": "#/components/headers/Cache-Control"}}},
    }

    parameters = {
        "DateRequired": {"name": "date", "in": "query", "required": True,
                         "schema": {"type": "string", "format": "date"},
                         "description": "ISO YYYY-MM-DD",
                         "example": "2026-05-19"},
        "DateOptional": {"name": "date", "in": "query", "required": False,
                         "schema": {"type": "string", "format": "date"},
                         "description": "ISO YYYY-MM-DD (default: latest report date)",
                         "example": "2026-05-19"},
        "RangeParam":   {"name": "range", "in": "query", "required": False,
                         "schema": {"type": "string",
                                    "enum": ["day", "week", "month", "3month"],
                                    "default": "month"},
                         "description": "Aggregation window"},
        "EndParam":     {"name": "end", "in": "query", "required": False,
                         "schema": {"type": "string", "format": "date"},
                         "description": "ISO YYYY-MM-DD (period end; default: latest)"},
        "SectionParam": {"name": "section", "in": "query", "required": False,
                         "schema": {"type": "integer", "enum": [1, 2]},
                         "description": "Optional filter: 1=製造１課, 2=製造２課"},
        "LimitParam":   {"name": "limit", "in": "query", "required": False,
                         "schema": {"type": "integer", "minimum": 1, "maximum": 1000},
                         "description": "Page size (list responses only)"},
        "OffsetParam":  {"name": "offset", "in": "query", "required": False,
                         "schema": {"type": "integer", "minimum": 0, "default": 0},
                         "description": "Page offset (list responses only)"},
        "IfNoneMatch":  {"name": "If-None-Match", "in": "header", "required": False,
                         "schema": {"type": "string"},
                         "description": "Send the ETag from a previous response to get a 304 if unchanged."},
    }

    def _200(envelope_ref, example=None):
        ok = {"description": "OK",
              "headers": {"ETag": {"$ref": "#/components/headers/ETag"},
                          "Cache-Control": {"$ref": "#/components/headers/Cache-Control"}},
              "content": {"application/json":
                          {"schema": {"$ref": envelope_ref}}}}
        if example is not None:
            ok["content"]["application/json"]["example"] = example
        return ok

    def _common_errors():
        return {
            "304": {"$ref": "#/components/responses/NotModified"},
            "401": {"$ref": "#/components/responses/Unauthorized"},
            "403": {"$ref": "#/components/responses/Forbidden"},
            "429": {"$ref": "#/components/responses/RateLimited"},
            "502": {"$ref": "#/components/responses/BadGateway"},
            "503": {"$ref": "#/components/responses/ServiceUnavailable"},
        }

    def _op(tag, summary, description, params, env_ref, example=None):
        rsp = {"200": _200(env_ref, example)}
        rsp.update(_common_errors())
        return {"get": {"tags": [tag],
                        "summary": summary,
                        "description": description,
                        "security": [{"bearerAuth": []}],
                        "parameters": params,
                        "responses": rsp}}

    Pref = lambda n: {"$ref": f"#/components/parameters/{n}"}

    info_md = (
        "Read-only company-to-company data API for GENBA FMS.\n\n"
        "**Authentication.** Every call sends `Authorization: Bearer <partner-token>` "
        "(or `X-Partner-Token: <partner-token>`). Tokens are issued per company and "
        "individually revocable.\n\n"
        "**Response envelope.** Success → `{ \"ok\": true, \"data\": …, \"meta\": { … } }`. "
        "Error → `{ \"ok\": false, \"error\": { \"code\": \"…\", \"message\": \"…\" } }`.\n\n"
        "**Caching.** Read endpoints return `ETag` and `Cache-Control: private, max-age=60`. "
        "Send `If-None-Match: <etag>` to receive `304 Not Modified`.\n\n"
        "**Pagination.** List responses accept `limit` and `offset`; `meta` reports "
        "`total / offset / limit / returned`.\n\n"
        "**Rate-limit & quota.** Each partner has its own per-minute rate limit and "
        "optional monthly quota. Over-limit responses return `429` with `Retry-After`.\n\n"
        "**Status codes.** `200` OK · `304` cached · `401` token problem · `403` "
        "partner disabled / IP not allowed · `429` rate limit / quota · `502` upstream "
        "hiccup · `503` API globally disabled by admin."
    )

    return {
        "openapi": "3.0.3",
        "info": {
            "title": "GENBA FMS Partner API",
            "version": API_VERSION,
            "description": info_md,
            "contact": {"name": "GENBA FMS admin", "url": "https://genbafms.com/"},
            "license": {"name": "Proprietary"},
        },
        "servers": [{"url": "https://api.genbafms.com/v1",
                     "description": "Production (public)"}],
        "tags": [
            {"name": "Health",       "description": "Auth/health check"},
            {"name": "Discovery",    "description": "List available datasets"},
            {"name": "Production",   "description": "Daily production + section summary"},
            {"name": "Productivity", "description": "Labor-productivity series + summary"},
            {"name": "Packs",        "description": "Per-item produced-packs rows"},
            {"name": "Attendance",   "description": "Per-employee attendance + totals"},
        ],
        "components": {
            "securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer",
                                               "description": "Per-partner bearer token (e.g. pt_…)"}},
            "parameters": parameters,
            "headers": headers,
            "responses": responses,
            "schemas": schemas,
        },
        "security": [{"bearerAuth": []}],
        "paths": {
            "/ping": _op("Health", "Auth & server-time check",
                         "Smoke test. Returns the calling partner name and the current "
                         "server time. Not cached.",
                         [Pref("IfNoneMatch")], "#/components/schemas/PingEnvelope",
                         example={"ok": True,
                                  "data": {"pong": True, "server_time": "2026-05-20T09:00:00"},
                                  "meta": {"partner": "ACME Co", "ts": "2026-05-20T09:00:00",
                                           "api_version": API_VERSION, "cached": False}}),
            "/datasets": _op("Discovery", "List available datasets",
                             "Self-describing list of the read endpoints available to "
                             "you. Useful for self-integration / discovery tooling.",
                             [Pref("LimitParam"), Pref("OffsetParam"), Pref("IfNoneMatch")],
                             "#/components/schemas/DatasetsEnvelope"),
            "/production": _op("Production", "Daily production + section summary",
                               "For the given date (default = latest report date): the "
                               "production totals, the per-section labor productivity "
                               "summary, and today's production plan.",
                               [Pref("DateOptional"), Pref("IfNoneMatch")],
                               "#/components/schemas/ProductionEnvelope"),
            "/productivity": _op("Productivity",
                                 "Labor-productivity series + summary",
                                 "Aggregated labor productivity for `range`, plus the "
                                 "matching prior period for comparison. Targets are "
                                 "S1=85 P/h, S2=35 P/h, Combined=25 P/h.",
                                 [Pref("RangeParam"), Pref("EndParam"), Pref("IfNoneMatch")],
                                 "#/components/schemas/ProductivityEnvelope"),
            "/packs": _op("Packs", "Per-item produced-packs rows",
                          "Per-item produced-packs rows for the given date.",
                          [Pref("DateRequired"), Pref("LimitParam"),
                           Pref("OffsetParam"), Pref("IfNoneMatch")],
                          "#/components/schemas/Envelope"),
            "/attendance": _op("Attendance",
                               "Per-employee attendance + totals",
                               "For a given date returns one row per employee — name, "
                               "code, section, clock-in/out, worked hours (HH:MM) and "
                               "minutes — plus grand totals and per-section totals. "
                               "Optionally filter to one section.",
                               [Pref("DateRequired"), Pref("SectionParam"),
                                Pref("LimitParam"), Pref("OffsetParam"), Pref("IfNoneMatch")],
                               "#/components/schemas/AttendanceEnvelope",
                               example={
                                   "ok": True,
                                   "data": {
                                       "date": "2026-05-19",
                                       "employees": [{
                                           "name": "山田 太郎", "code": "00007001",
                                           "section_id": 1, "section": "製造１課",
                                           "in": "10:44", "out": "19:17",
                                           "hours": "8:33", "minutes": 513, "is_temp": False,
                                       }],
                                       "totals": {"employees": 7, "present": 3,
                                                  "total_hours_hhmm": "28:15",
                                                  "total_hours": 28.25,
                                                  "by_section": [
                                                      {"id": 1, "label": "製造１課",
                                                       "employees": 3, "present": 0,
                                                       "total_hours_hhmm": "0:00", "total_hours": 0.0}]},
                                   },
                                   "meta": {"partner": "ACME Co", "ts": "2026-05-20T09:00:00",
                                            "api_version": API_VERSION, "cached": False,
                                            "total": 7, "offset": 0, "limit": 7, "returned": 7},
                               }),
        },
    }


@router.api_route("/openapi.json", methods=["GET", "HEAD"])
def partner_openapi(request: Request):
    # Spec is the public contract — no token needed, but honour the kill-switch.
    if not _load().get("enabled"):
        raise PartnerAPIError(503, "api_disabled", "Partner API is disabled.")
    return JSONResponse(_openapi_spec(),
                        headers={"Cache-Control": "public, max-age=900"})


@router.api_route("/docs", methods=["GET", "HEAD"], response_class=HTMLResponse)
def partner_docs(request: Request):
    if not _load().get("enabled"):
        raise PartnerAPIError(503, "api_disabled", "Partner API is disabled.")
    return HTMLResponse("""<!doctype html><html><head><meta charset=utf-8>
<title>GENBA FMS Partner API — Docs</title>
<link rel=stylesheet href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
<style>.fb{padding:8px 14px;font:13px system-ui,sans-serif;background:#eef3f5;border-bottom:1px solid #d4e2e8;}</style>
</head><body>
<div class="fb">No JavaScript? Read the spec at
<a href="openapi.json">openapi.json</a> or the plain-text reference at
<a href="docs.md">docs.md</a>.</div>
<div id=ui></div>
<script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>SwaggerUIBundle({url:'openapi.json',dom_id:'#ui',
persistAuthorization:true});</script></body></html>""",
        headers={"Cache-Control": "public, max-age=900"})


def _spec_to_markdown(spec: dict) -> str:
    """Render the OpenAPI dict to a human-readable Markdown reference.
    Used by /docs.md so non-JS clients (curl, AI viewers, simple browsers)
    can read the API without running Swagger UI."""
    info = spec.get("info") or {}
    out: list = []
    out.append(f"# {info.get('title','API')} — Reference (v{info.get('version','')})\n\n")
    if info.get("description"):
        out.append(info["description"].rstrip() + "\n\n")
    servers = spec.get("servers") or []
    if servers:
        out.append("## Servers\n\n")
        for s in servers:
            out.append(f"- `{s.get('url','')}` — {s.get('description','') or ''}".rstrip() + "\n")
        out.append("\n")
    out.append("## Authentication\n\nEvery call requires "
               "`Authorization: Bearer <partner-token>` "
               "(`X-Partner-Token: <partner-token>` also accepted).\n\n")
    params_pool = (spec.get("components") or {}).get("parameters") or {}
    out.append("## Endpoints\n")
    for path, methods in (spec.get("paths") or {}).items():
        for method, ent in methods.items():
            out.append(f"\n### {method.upper()} {path}\n\n")
            if ent.get("summary"):
                out.append(f"**{ent['summary']}**\n\n")
            if ent.get("description"):
                out.append(ent["description"].rstrip() + "\n\n")
            resolved = []
            for p in ent.get("parameters") or []:
                if isinstance(p, dict) and "$ref" in p:
                    key = p["$ref"].rsplit("/", 1)[-1]
                    p = params_pool.get(key, {}) or {}
                resolved.append(p)
            if resolved:
                out.append("| Param | In | Type | Required | Description |\n"
                           "|---|---|---|---|---|\n")
                for p in resolved:
                    sch = p.get("schema") or {}
                    typ = sch.get("type", "")
                    if sch.get("enum"):
                        typ += f" ({'|'.join(map(str, sch['enum']))})"
                    if sch.get("format"):
                        typ += f", {sch['format']}"
                    desc = (p.get("description") or "").replace("\n", " ").strip()
                    req = "yes" if p.get("required") else "no"
                    out.append(f"| `{p.get('name','')}` | {p.get('in','')} | "
                               f"{typ} | {req} | {desc} |\n")
                out.append("\n")
            resps = ent.get("responses") or {}
            if resps:
                out.append("Responses: " + ", ".join(sorted(resps.keys())) + "\n\n")
            ok = resps.get("200") or {}
            ex = ((ok.get("content") or {}).get("application/json") or {}).get("example")
            if ex is not None:
                out.append("Example response:\n\n```json\n"
                           + json.dumps(ex, indent=2, ensure_ascii=False)
                           + "\n```\n\n")
    err_enum = ((((spec.get("components") or {}).get("schemas") or {})
                 .get("ErrorEnvelope") or {})
                .get("properties", {}).get("error", {}).get("properties", {})
                .get("code", {}).get("enum") or [])
    if err_enum:
        out.append("## Error codes\n\n")
        for c in err_enum:
            out.append(f"- `{c}`\n")
        out.append("\n")
    out.append("## Status codes\n\n"
               "`200` OK · `304` cached (If-None-Match matched) · "
               "`401` token problem · `403` partner disabled / IP not allowed · "
               "`429` rate limit or monthly quota · `502` upstream hiccup · "
               "`503` API globally disabled.\n")
    return "".join(out)


@router.api_route("/docs.md", methods=["GET", "HEAD"])
def partner_docs_md(request: Request):
    """Plain-text Markdown reference — for clients that can't execute JS
    (curl, AI viewers, simple readers). Same source spec as /docs."""
    if not _load().get("enabled"):
        raise PartnerAPIError(503, "api_disabled", "Partner API is disabled.")
    md = _spec_to_markdown(_openapi_spec())
    return PlainTextResponse(md,
                             media_type="text/markdown; charset=utf-8",
                             headers={"Cache-Control": "public, max-age=900"})


# ---- admin helpers (called by main.py's admin-gated endpoints) ------------
def partner_status() -> dict:
    cfg = _load()
    parts = []
    for p in cfg.get("partners", []):
        st = _STAT.get(p["id"], {})
        today, month = _usage_counts(p["id"])
        parts.append({
            "id": p["id"], "name": p.get("name"),
            "disabled": bool(p.get("disabled")),
            "rate_per_min": p.get("rate_per_min", 60),
            "monthly_quota": int(p.get("monthly_quota", 0) or 0),
            "ip_allowlist": p.get("ip_allowlist") or [],
            "created_at": p.get("created_at"),
            "calls": st.get("calls", 0),
            "usage_today": today,
            "usage_month": month,
            "last_seen": st.get("last_seen"),
            "last_ip": st.get("last_ip"),
            "token_tail": ("…" + str(p.get("token", ""))[-6:]) if p.get("token") else "",
        })
    return {"enabled": bool(cfg.get("enabled")), "count": len(parts),
            "api_version": API_VERSION, "partners": parts}


def partner_set_enabled(enabled: bool) -> dict:
    cfg = _load()
    cfg["enabled"] = bool(enabled)
    _save(cfg)
    print(f"[PARTNER_API] enabled={cfg['enabled']}")
    return partner_status()


def partner_add(name: str, rate_per_min: int = 60,
                ip_allowlist: list | None = None,
                monthly_quota: int = 0) -> dict:
    cfg = _load()
    pid = "p_" + secrets.token_hex(4)
    token = "pt_" + secrets.token_urlsafe(28)
    cfg.setdefault("partners", []).append({
        "id": pid, "name": (name or "partner").strip()[:80],
        "token": token, "rate_per_min": int(rate_per_min or 60),
        "monthly_quota": int(monthly_quota or 0),
        "ip_allowlist": [s.strip() for s in (ip_allowlist or []) if s.strip()],
        "disabled": False,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    })
    _save(cfg)
    return {"ok": True, "id": pid, "name": name, "token": token}


def partner_update(pid: str, disabled: bool | None = None,
                   rate_per_min: int | None = None,
                   ip_allowlist: list | None = None,
                   monthly_quota: int | None = None) -> dict:
    cfg = _load()
    for p in cfg.get("partners", []):
        if p["id"] == pid:
            if disabled is not None:
                p["disabled"] = bool(disabled)
            if rate_per_min is not None:
                p["rate_per_min"] = int(rate_per_min)
            if monthly_quota is not None:
                p["monthly_quota"] = int(monthly_quota)
            if ip_allowlist is not None:
                p["ip_allowlist"] = [s.strip() for s in ip_allowlist if s.strip()]
            _save(cfg)
            return {"ok": True}
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="partner not found")


def partner_revoke(pid: str) -> dict:
    cfg = _load()
    before = len(cfg.get("partners", []))
    cfg["partners"] = [p for p in cfg.get("partners", []) if p["id"] != pid]
    _save(cfg)
    _RT.pop(pid, None)
    _STAT.pop(pid, None)
    with _usage_lock:
        _USAGE.pop(pid, None)
    _usage_flush(force=True)
    return {"ok": True, "removed": before - len(cfg["partners"])}


def partner_log_tail(limit: int = 100) -> dict:
    limit = max(1, min(int(limit or 100), 1000))
    items: list = []
    size = 0
    if PARTNER_LOG_PATH.exists():
        try:
            size = PARTNER_LOG_PATH.stat().st_size
            with PARTNER_LOG_PATH.open("r", encoding="utf-8") as fh:
                tail = fh.readlines()[-limit:]
            for raw in tail:
                raw = raw.strip()
                if raw:
                    try:
                        items.append(json.loads(raw))
                    except Exception:
                        pass
        except Exception as exc:
            return {"path": str(PARTNER_LOG_PATH), "error": str(exc), "items": []}
    return {
        "path": str(PARTNER_LOG_PATH),
        "file_size_bytes": size,
        "status": partner_status(),
        "count": len(items),
        "items": list(reversed(items)),
    }
