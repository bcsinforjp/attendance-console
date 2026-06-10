"""
agent_api.py — unified AI-Agent API (REST) + MCP server.

A single bearer token per agent unlocks two front doors onto the same trusted
internal endpoints:

  * REST   — /api/agent/v1/*   (curl/HTTP, OpenAPI-ish discovery)
  * MCP    — /mcp              (Model Context Protocol, JSON-RPC tools)

Both authenticate the caller with the agent token, then reach the app's own
endpoints over http://127.0.0.1 (loopback bypasses the host-auth middleware, so
the existing internal write handlers are reachable server-side while the external
caller is gated solely by the agent token).

Capabilities (per owner decision):
  READ   production, productivity, packs, attendance, roster, day-off, history
  WRITE  pack counts + temp-staff only   (gated by per-token `write_enabled`)
  CHANGE submit/track feature requests   (Part B — change_requests.py ledger)
  NEVER  deletes, roster/day-off writes, uploads, user/key/admin, app-update

Modelled on partner_api.py (deny-by-default, per-token revocable + rate-limited +
IP-allowlistable). Kept independent — partner_api.py is untouched.

main.py wires it:
    from agent_api import router, mcp_app, register_agent_error_handler, agent_* ...
    app.include_router(router); register_agent_error_handler(app)
    app.mount("/mcp", mcp_app)
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import requests
from fastapi import APIRouter, Request, Body
from fastapi.responses import JSONResponse, Response, PlainTextResponse
from starlette.responses import JSONResponse as SJSONResponse, Response as SResponse
from starlette.concurrency import run_in_threadpool

import change_requests as cr

BASE_DIR = Path(__file__).resolve().parent
AGENT_CONFIG_PATH = BASE_DIR / "agent_api.json"

_LOG_DIR = Path(os.environ.get("AI_SERVER_LOG_DIR", "/var/log/ai_server"))
try:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
except PermissionError:
    _LOG_DIR = BASE_DIR / "logs"
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
AGENT_LOG_PATH = _LOG_DIR / "agent_api_requests.jsonl"

SELF_BASE = f"http://127.0.0.1:{os.environ.get('ATTENDANCE_SELF_PORT', '8002')}"
API_VERSION = "1.0"

router = APIRouter(prefix="/api/agent/v1", tags=["agent-api"])


# ---- error type (enveloped, machine codes) --------------------------------
class AgentAPIError(Exception):
    def __init__(self, status: int, code: str, message: str, headers: dict | None = None):
        self.status = status
        self.code = code
        self.message = message
        self.headers = headers or {}
        super().__init__(message)


def register_agent_error_handler(app) -> None:
    """Scoped error envelope — only fires for AgentAPIError, so the rest of the
    app's error shape is untouched."""
    @app.exception_handler(AgentAPIError)
    async def _handle(request: Request, exc: AgentAPIError):
        return JSONResponse(
            status_code=exc.status,
            content={"ok": False, "error": {"code": exc.code, "message": exc.message}},
            headers=exc.headers,
        )


# ---- config helpers --------------------------------------------------------
def _load() -> dict:
    try:
        if AGENT_CONFIG_PATH.exists():
            d = json.loads(AGENT_CONFIG_PATH.read_text(encoding="utf-8"))
            d.setdefault("enabled", False)
            d.setdefault("agents", [])
            return d
    except Exception as exc:
        print(f"[AGENT_API] config read failed: {exc}")
    return {"enabled": False, "agents": []}


def _save(cfg: dict) -> None:
    tmp = AGENT_CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(AGENT_CONFIG_PATH)
    try:
        os.chmod(AGENT_CONFIG_PATH, 0o600)
    except Exception:
        pass


_RT: dict = {}      # aid -> [window_start_epoch, count]
_STAT: dict = {}    # aid -> {calls,last_seen,last_ip}

# Optional OAuth bearer-token resolver (set by main.py → mcp_oauth.resolve_token).
# Lets the MCP/REST auth accept OAuth access tokens (mat_…) in addition to the
# static at_… tokens, mapping them to a managed agent id. Injected to avoid an
# import cycle (mcp_oauth imports agent_api).
_OAUTH_RESOLVER = None


def set_oauth_resolver(fn) -> None:
    global _OAUTH_RESOLVER
    _OAUTH_RESOLVER = fn


def _mcp_base(request: Request) -> str:
    host = (request.headers.get("x-forwarded-host")
            or request.headers.get("host") or "link.genbafms.com")
    proto = "http" if host.startswith(("127.", "localhost")) else "https"
    return f"{proto}://{host}"


def ensure_oauth_agent(agent_id: str, name: str, write_enabled: bool = True) -> dict:
    """Get-or-create a managed agent record bound to an OAuth client. Enables the
    API on first connect (the admin just approved it via password). Appears in
    /admin → Agent API and is revocable like any other agent."""
    cfg = _load()
    for a in cfg.get("agents", []):
        if a["id"] == agent_id:
            if not cfg.get("enabled"):
                cfg["enabled"] = True
                _save(cfg)
            return a
    rec = {"id": agent_id, "name": (name or "Claude connector").strip()[:80],
           "token": "(oauth)", "rate_per_min": 120, "ip_allowlist": [],
           "disabled": False, "write_enabled": bool(write_enabled), "oauth": True,
           "created_at": datetime.now().isoformat(timespec="seconds")}
    cfg.setdefault("agents", []).append(rec)
    cfg["enabled"] = True
    _save(cfg)
    return rec


def _client_ip(request: Request) -> str:
    return (
        request.headers.get("x-real-ip")
        or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "?")
    )


def _log(agent_id: str, name: str, ip: str, path: str, status: int, ms: int) -> None:
    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "agent_id": agent_id, "agent": name, "ip": ip,
        "path": path, "status": status, "duration_ms": ms,
    }
    try:
        with AGENT_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if AGENT_LOG_PATH.stat().st_size > 5 * 1024 * 1024:
            lines = AGENT_LOG_PATH.read_text(encoding="utf-8").splitlines()[-4000:]
            AGENT_LOG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception as exc:
        print(f"[AGENT_API] log write failed: {exc}")


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("x-agent-token") or None


def _require_agent(request: Request) -> dict:
    """Auth + abuse gate. Raises AgentAPIError; returns the agent record."""
    cfg = _load()
    if not cfg.get("enabled"):
        raise AgentAPIError(503, "api_disabled", "Agent API is disabled.")
    token = _extract_token(request)
    if not token:
        raise AgentAPIError(401, "missing_token",
                            "Provide Authorization: Bearer <token>.")
    agent = None
    for a in cfg.get("agents", []):
        if a.get("token") and secrets.compare_digest(str(a.get("token", "")), token):
            agent = a
            break
    if agent is None and _OAUTH_RESOLVER is not None:
        aid = _OAUTH_RESOLVER(token)
        if aid:
            for a in cfg.get("agents", []):
                if a.get("id") == aid:
                    agent = a
                    break
    if agent is None:
        raise AgentAPIError(401, "invalid_token", "Invalid agent token.")
    if agent.get("disabled"):
        raise AgentAPIError(403, "agent_disabled", "This agent is disabled.")
    ip = _client_ip(request)
    allow = agent.get("ip_allowlist") or []
    if allow and ip not in allow:
        raise AgentAPIError(403, "ip_not_allowed",
                            "Source IP not allowed for this agent.")
    aid = agent["id"]
    rpm = int(agent.get("rate_per_min", 60) or 60)
    now = time.time()
    win = _RT.get(aid)
    if not win or (now - win[0]) >= 60:
        _RT[aid] = [now, 0]
        win = _RT[aid]
    win[1] += 1
    if win[1] > rpm:
        retry = max(1, int(60 - (now - win[0])))
        raise AgentAPIError(429, "rate_limited",
                            f"Rate limit exceeded ({rpm}/min).",
                            {"Retry-After": str(retry)})
    st = _STAT.setdefault(aid, {"calls": 0})
    st["calls"] += 1
    st["last_seen"] = datetime.now().isoformat(timespec="seconds")
    st["last_ip"] = ip
    return agent


def _require_write(agent: dict) -> None:
    if not agent.get("write_enabled", True):
        raise AgentAPIError(403, "write_disabled",
                            "This agent token is read-only (write_enabled=false).")


# ---- upstream proxy helpers ------------------------------------------------
# Tiny in-memory TTL cache for proxied READS. Production data changes on a
# minute scale (uploads/edits), so an 8s cache makes repeated polls (HMI every
# 15s, dashboards, agents re-reading) skip the loopback hop + DB query entirely.
# Any write via _proxy_write clears the cache so reads reflect it immediately.
_CACHE: dict = {}                 # path -> (expires_at, data)
_CACHE_TTL = 8.0                  # seconds
_cache_lock = threading.Lock()


def _cache_clear() -> None:
    with _cache_lock:
        _CACHE.clear()


def _proxy_json(path: str, ttl: float = _CACHE_TTL):
    """GET a trusted internal endpoint over localhost; return parsed JSON.
    Short-TTL cached so repeated reads are near-instant."""
    now = time.time()
    if ttl > 0:
        with _cache_lock:
            hit = _CACHE.get(path)
            if hit and hit[0] > now:
                return hit[1]
    url = SELF_BASE + path
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise AgentAPIError(502, "upstream_unavailable",
                            f"Upstream data unavailable: {exc}")
    if ttl > 0:
        with _cache_lock:
            _CACHE[path] = (now + ttl, data)
            if len(_CACHE) > 256:   # bound size — drop expired entries
                for k in [k for k, v in _CACHE.items() if v[0] <= now]:
                    _CACHE.pop(k, None)
    return data


def _proxy_write(method: str, path: str, body: dict):
    """POST/PUT a trusted internal endpoint over loopback.

    IMPORTANT (load-bearing contract): the URL host is 127.0.0.1, so the request
    Host header is NOT in GBL_AUTH_HOSTS and the genbalink_host_auth middleware
    does NOT gate it. That is what lets us reach the (session-only) internal write
    handlers server-side. Do NOT set a genbafms Host header here — it would re-arm
    the gate and the write would 401.
    """
    url = SELF_BASE + path
    try:
        r = requests.request(method, url, json=body,
                             headers={"Accept": "application/json"}, timeout=30)
    except requests.RequestException as exc:
        raise AgentAPIError(502, "upstream_unavailable", f"Upstream write failed: {exc}")
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail")
        except Exception:
            detail = r.text[:300]
        code = {400: "bad_request", 409: "duplicate", 423: "ingestion_paused"}.get(
            r.status_code, "upstream_error")
        status = r.status_code if r.status_code in (400, 409, 423) else 502
        raise AgentAPIError(status, code, str(detail))
    _cache_clear()   # a write happened → drop cached reads so they reflect it
    try:
        return r.json()
    except Exception:
        return {"ok": True}


# ---- response envelope (ETag/304 on reads) --------------------------------
def _envelope(request: Request, agent: dict, data, *,
              extra_meta: dict | None = None, max_age: int = 60,
              status: int = 200) -> Response:
    import hashlib
    meta = {
        "agent": agent.get("name"),
        "ts": datetime.now().isoformat(timespec="seconds"),
        "api_version": API_VERSION,
    }
    if extra_meta:
        meta.update(extra_meta)
    body = {"ok": True, "data": data, "meta": meta}
    raw = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
    etag = 'W/"%s"' % hashlib.sha1(raw).hexdigest()[:20]
    ms = int((time.time() - getattr(request.state, "_t0", time.time())) * 1000)
    inm = request.headers.get("if-none-match", "")
    rt = f"{ms}ms"
    if max_age > 0 and inm and etag in [t.strip() for t in inm.split(",")]:
        _log(agent["id"], agent.get("name", "?"), _client_ip(request),
             request.url.path, 304, ms)
        return Response(status_code=304, headers={
            "ETag": etag, "Cache-Control": f"private, max-age={max_age}",
            "X-Response-Time": rt})
    cc = f"private, max-age={max_age}" if max_age > 0 else "no-store"
    _log(agent["id"], agent.get("name", "?"), _client_ip(request),
         request.url.path, status, ms)
    return JSONResponse(status_code=status, content=body,
                        headers={"ETag": etag, "Cache-Control": cc,
                                 "X-Response-Time": rt})


def _paginate(data, limit, offset):
    meta = {}
    seq = None
    target_key = None
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


# ---- reshape helpers (shared with MCP) ------------------------------------
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


def _attendance_data(date: str, section: int | None = None) -> dict:
    g = _proxy_json(f"/api/gantt/{date}")
    employees, by_section = [], []
    for s in (g.get("sections") or []):
        if section and s.get("id") != section:
            continue
        rows = s.get("rows") or []
        s_min = s_present = 0
        for r in rows:
            mins = _hhmm_to_min(r.get("wh"))
            if mins > 0:
                s_present += 1
            s_min += mins
            employees.append({
                "name": r.get("name"), "code": r.get("code"),
                "section_id": s.get("id"), "section": s.get("label"),
                "in": r.get("in"), "out": r.get("out"),
                "hours": r.get("wh"), "minutes": mins,
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
    return {"date": g.get("date"), "employees": employees, "totals": totals}


def _attendance_range_data(employee_code: str, start: str, end: str,
                           section: int | None = None) -> dict:
    """One employee's per-day attendance over a date range, minimal payload.
    Proxies /api/members/compare (range + employee filter, indexed
    attendance_records) — one request instead of one-per-day. Change request #4."""
    g = _proxy_json(f"/api/members/compare?from={start}&to={end}&codes={employee_code}")
    members = g.get("members") or []
    if not members:
        return {"employee_code": employee_code, "name": None, "section_id": None,
                "start": start, "end": end, "days": [], "total_minutes": 0,
                "present_days": 0}
    m = members[0]
    if section and m.get("section_id") != section:
        return {"employee_code": employee_code, "name": m.get("name"),
                "section_id": m.get("section_id"), "start": start, "end": end,
                "days": [], "total_minutes": 0, "present_days": 0,
                "note": "employee not in requested section"}
    days, total = [], 0
    for d in (m.get("days") or []):
        mins = _hhmm_to_min(d.get("in") and d.get("out") and
                            _min_to_hhmm(int(round((d.get("work_hours") or 0) * 60))))
        if not mins:
            mins = int(round((d.get("work_hours") or 0) * 60))
        i, o = d.get("in"), d.get("out")
        anomaly = None
        if i and not o:
            anomaly = "missing_out"
        elif o and not i:
            anomaly = "missing_in"
        elif not i and not o and mins == 0:
            anomaly = None  # simply absent / no record
        total += mins
        days.append({"date": d.get("date"), "minutes": mins, "in": i, "out": o,
                     "anomaly": anomaly})
    return {"employee_code": employee_code, "name": m.get("name"),
            "section_id": m.get("section_id"), "section": m.get("section_label"),
            "start": start, "end": end, "days": days,
            "present_days": sum(1 for d in days if d["minutes"] > 0),
            "total_minutes": total, "total_hours_hhmm": _min_to_hhmm(total)}


def _attendance_export_rows(start: str, end: str, section: int | None = None) -> list:
    """ALL employees' daily attendance over a range (≤92 days) in one shot.
    Batches the indexed /api/members/compare (30 codes/call) so a company-wide
    multi-week pull is one agent call — change request #5 (P1-2)."""
    try:
        sd = datetime.strptime(start, "%Y-%m-%d")
        ed = datetime.strptime(end, "%Y-%m-%d")
    except Exception:
        raise AgentAPIError(400, "bad_request", "start/end must be YYYY-MM-DD")
    if ed < sd:
        raise AgentAPIError(400, "bad_request", "end is before start")
    if (ed - sd).days > 92:
        raise AgentAPIError(400, "bad_request",
                            "range cannot exceed 92 days — request smaller windows")
    sec = str(section) if section in (1, 2) else "all"
    members = (_proxy_json(f"/api/members/list?section={sec}") or {}).get("items", [])
    codes = [m["code"] for m in members if m.get("code")]
    name_by = {m["code"]: m.get("name") for m in members}
    sec_by = {m["code"]: m.get("section_id") for m in members}
    rows = []
    for i in range(0, len(codes), 30):
        batch = codes[i:i + 30]
        g = _proxy_json(f"/api/members/compare?from={start}&to={end}&codes={','.join(batch)}")
        for m in (g.get("members") or []):
            c = m.get("code")
            for d in (m.get("days") or []):
                mins = int(round((d.get("work_hours") or 0) * 60))
                iv, ov = d.get("in"), d.get("out")
                an = "missing_out" if (iv and not ov) else ("missing_in" if (ov and not iv) else None)
                rows.append({"code": c, "name": m.get("name") or name_by.get(c),
                             "section_id": m.get("section_id") or sec_by.get(c),
                             "date": d.get("date"), "minutes": mins,
                             "in": iv, "out": ov, "anomaly": an})
    rows.sort(key=lambda r: (r["date"] or "", r["code"] or ""))
    return rows


def _attendance_summary_rows(start: str, end: str, section: int | None = None) -> list:
    """Per-employee monthly/range summary (change request #6): days worked, total
    hours, overtime (>8h/day), absent days, attendance rate. Aggregates the daily
    export. Overtime = minutes over 480/day."""
    daily = _attendance_export_rows(start, end, section)
    agg: dict = {}
    for r in daily:
        c = r["code"]
        a = agg.get(c)
        if a is None:
            a = agg[c] = {"code": c, "name": r["name"], "section_id": r["section_id"],
                          "present_days": 0, "absent_days": 0,
                          "total_minutes": 0, "overtime_minutes": 0}
        m = r["minutes"] or 0
        if m > 0:
            a["present_days"] += 1
        else:
            a["absent_days"] += 1
        a["total_minutes"] += m
        a["overtime_minutes"] += max(0, m - 480)
    out = []
    for a in agg.values():
        days = a["present_days"] + a["absent_days"]
        a["total_hours_hhmm"] = _min_to_hhmm(a["total_minutes"])
        a["overtime_hhmm"] = _min_to_hhmm(a["overtime_minutes"])
        a["attendance_rate_pct"] = round(a["present_days"] / days * 100, 1) if days else 0
        out.append(a)
    out.sort(key=lambda x: (x["section_id"] or 0, x["code"] or ""))
    return out


# ===========================================================================
#  REST — read endpoints
# ===========================================================================
@router.get("/ping")
def agent_ping(request: Request):
    request.state._t0 = time.time()
    a = _require_agent(request)
    return _envelope(request, a, {
        "pong": True, "write_enabled": bool(a.get("write_enabled", True)),
        "server_time": datetime.now().isoformat(timespec="seconds"),
    }, max_age=0)


@router.get("/datasets")
def agent_datasets(request: Request):
    request.state._t0 = time.time()
    a = _require_agent(request)
    sets = {
        "reads": [
            {"path": "/api/agent/v1/production?date=YYYY-MM-DD", "desc": "production + productivity snapshot"},
            {"path": "/api/agent/v1/productivity?range=month&end=YYYY-MM-DD", "desc": "labor productivity series (day|week|month|3month)"},
            {"path": "/api/agent/v1/packs?date=YYYY-MM-DD", "desc": "per-item produced-packs for a date"},
            {"path": "/api/agent/v1/attendance?date=YYYY-MM-DD&section=1|2", "desc": "per-employee attendance + totals"},
            {"path": "/api/agent/v1/attendance-range?employee_code=&start=&end=&section=1|2", "desc": "ONE employee's daily attendance over a date range (1 call, minimal payload)"},
            {"path": "/api/agent/v1/attendance-export?start=&end=&section=1|2&format=json|csv", "desc": "ALL employees' daily attendance over a range (≤92 days) in one call; CSV download available"},
            {"path": "/api/agent/v1/roster", "desc": "employee roster (read-only)"},
            {"path": "/api/agent/v1/dayoff", "desc": "day-off schedule (read-only)"},
            {"path": "/api/agent/v1/packs/{date}/history", "desc": "pack-count audit trail for a date"},
        ],
        "writes": [
            {"path": "POST /api/agent/v1/packs", "desc": "upsert pack count {record_date,number_of_packs,note?}"},
            {"path": "POST /api/agent/v1/packs/bulk", "desc": "bulk upsert {entries:[...]}"},
            {"path": "POST /api/agent/v1/temp-staff", "desc": "replace temp staff for a date {record_date,rows:[...]}"},
        ],
        "change_management": [
            {"path": "POST /api/agent/v1/requests", "desc": "submit a feature/system request {title,body,category?}"},
            {"path": "GET /api/agent/v1/requests", "desc": "list your requests"},
            {"path": "GET /api/agent/v1/requests/{id}", "desc": "request detail + conversation"},
            {"path": "POST /api/agent/v1/requests/{id}/messages", "desc": "post a message {message}"},
            {"path": "POST /api/agent/v1/requests/{id}/feedback", "desc": "report results {results?,issues?,completion_status}"},
        ],
        "notes": "Writes require write_enabled on your token. Date rules: report date = production date = attendance date + 1.",
    }
    return _envelope(request, a, sets, max_age=600)


@router.get("/openapi.json")
def agent_openapi(request: Request):
    """Public OpenAPI 3.1 schema — import into a ChatGPT Custom GPT Action or any
    OpenAPI client. No token required to READ the schema; calls still need the
    Bearer token (configure it as the Action's authentication)."""
    base = SELF_BASE
    fwd_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if fwd_host and "127.0.0.1" not in fwd_host:
        base = f"https://{fwd_host}"
    def env(desc):
        return {"200": {"description": desc, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Envelope"}}}}}
    P = "/api/agent/v1"
    spec = {
        "openapi": "3.1.0",
        "info": {"title": "GENBA FMS AI-Agent API", "version": API_VERSION,
                 "description": "Read/write factory data and file change requests with one bearer token."},
        "servers": [{"url": base}],
        "security": [{"bearerAuth": []}],
        "components": {
            "securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}},
            "schemas": {"Envelope": {"type": "object", "properties": {
                "ok": {"type": "boolean"}, "data": {"type": "object"},
                "meta": {"type": "object"}}}},
        },
        "paths": {
            f"{P}/ping": {"get": {"operationId": "ping", "summary": "Check the token and server time.", "responses": env("pong")}},
            f"{P}/production": {"get": {"operationId": "getProduction", "summary": "Production + productivity snapshot for a date (default latest).",
                "parameters": [{"name": "date", "in": "query", "required": False, "schema": {"type": "string"}, "description": "YYYY-MM-DD"}], "responses": env("snapshot")}},
            f"{P}/productivity": {"get": {"operationId": "getProductivity", "summary": "Labor-productivity series + prior period.",
                "parameters": [{"name": "range", "in": "query", "schema": {"type": "string", "enum": ["day", "week", "month", "3month"]}},
                               {"name": "end", "in": "query", "schema": {"type": "string"}, "description": "YYYY-MM-DD"}], "responses": env("series")}},
            f"{P}/packs": {"get": {"operationId": "getPacks", "summary": "Per-item produced packs for a date.",
                "parameters": [{"name": "date", "in": "query", "required": True, "schema": {"type": "string"}}], "responses": env("packs")},
                "post": {"operationId": "setPackCount", "summary": "Set/correct the produced-pack total for one date (audit-logged).",
                "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object", "required": ["record_date", "number_of_packs"],
                    "properties": {"record_date": {"type": "string"}, "number_of_packs": {"type": "integer"}, "note": {"type": "string"}}}}}}, "responses": env("saved")}},
            f"{P}/packs/bulk": {"post": {"operationId": "setPackCountsBulk", "summary": "Upsert pack counts for several dates.",
                "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object", "properties": {"entries": {"type": "array", "items": {"type": "object"}}}}}}}, "responses": env("saved")}},
            f"{P}/attendance": {"get": {"operationId": "getAttendance", "summary": "Per-employee attendance + totals for a date.",
                "parameters": [{"name": "date", "in": "query", "required": True, "schema": {"type": "string"}},
                               {"name": "section", "in": "query", "schema": {"type": "integer", "enum": [1, 2]}}], "responses": env("attendance")}},
            f"{P}/temp-staff": {"post": {"operationId": "setTempStaff", "summary": "Replace temp/Fullcast staff rows for one date.",
                "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object", "required": ["record_date", "rows"],
                    "properties": {"record_date": {"type": "string"}, "rows": {"type": "array", "items": {"type": "object"}}}}}}}, "responses": env("saved")}},
            f"{P}/roster": {"get": {"operationId": "getRoster", "summary": "Employee roster.",
                "parameters": [{"name": "section", "in": "query", "schema": {"type": "string", "enum": ["all", "1", "2"]}}], "responses": env("roster")}},
            f"{P}/dayoff": {"get": {"operationId": "getDayoff", "summary": "Day-off schedule.", "responses": env("dayoff")}},
            f"{P}/requests": {
                "get": {"operationId": "listRequests", "summary": "List your change requests.", "responses": env("requests")},
                "post": {"operationId": "submitRequest", "summary": "Submit a feature/system change request.",
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object", "required": ["title", "body"],
                        "properties": {"title": {"type": "string"}, "body": {"type": "string"}, "category": {"type": "string", "enum": ["feature", "system", "change", "bug"]}}}}}}, "responses": env("created")}},
            f"{P}/requests/{{req_id}}": {"get": {"operationId": "getRequest", "summary": "Get one change request + conversation.",
                "parameters": [{"name": "req_id", "in": "path", "required": True, "schema": {"type": "integer"}}], "responses": env("request")}},
            f"{P}/requests/{{req_id}}/feedback": {"post": {"operationId": "postRequestFeedback", "summary": "Report results/issues/completion on a request.",
                "parameters": [{"name": "req_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object", "required": ["completion_status"],
                    "properties": {"results": {"type": "string"}, "issues": {"type": "string"}, "completion_status": {"type": "string", "enum": ["in_progress", "completed", "failed", "blocked"]}}}}}}, "responses": env("ok")}},
        },
    }
    return JSONResponse(spec)


@router.get("/production")
def agent_production(request: Request, date: str | None = None):
    request.state._t0 = time.time()
    a = _require_agent(request)
    snap = _proxy_json("/api/dashboard/snapshot" + (f"?date={date}" if date else ""))
    out = {"report_date": snap.get("report_date"), "today": snap.get("today"),
           "productivity": snap.get("productivity"), "plan": snap.get("plan")}
    return _envelope(request, a, out, max_age=60)


@router.get("/productivity")
def agent_productivity(request: Request, range: str = "month", end: str | None = None):
    request.state._t0 = time.time()
    a = _require_agent(request)
    q = f"?range={range}" + (f"&end={end}" if end else "")
    return _envelope(request, a, _proxy_json("/api/productivity" + q), max_age=60)


@router.get("/packs")
def agent_packs(request: Request, date: str, limit: int | None = None, offset: int = 0):
    request.state._t0 = time.time()
    a = _require_agent(request)
    data = _proxy_json(f"/api/daily-packs/items/{date}")
    page, pm = _paginate(data, limit, offset)
    return _envelope(request, a, page, extra_meta=pm, max_age=60)


@router.get("/attendance")
def agent_attendance(request: Request, date: str, section: int | None = None,
                     limit: int | None = None, offset: int = 0):
    request.state._t0 = time.time()
    a = _require_agent(request)
    data = _attendance_data(date, section)
    page, pm = _paginate(data["employees"], limit, offset)
    out = {"date": data["date"], "employees": page, "totals": data["totals"]}
    return _envelope(request, a, out, extra_meta=pm, max_age=60)


@router.get("/attendance-range")
def agent_attendance_range(request: Request, employee_code: str, start: str, end: str,
                           section: int | None = None):
    """One employee's daily attendance over a date range in a single call
    (change request #4) — minimal payload, backed by the indexed attendance_records."""
    request.state._t0 = time.time()
    a = _require_agent(request)
    return _envelope(request, a, _attendance_range_data(employee_code, start, end, section), max_age=60)


@router.get("/attendance-export")
def agent_attendance_export(request: Request, start: str, end: str,
                            section: int | None = None, format: str = "json"):
    """ALL employees' daily attendance over a range (≤92 days) in one call.
    `format=csv` returns a CSV download; default JSON. Change request #5 (P1-2)."""
    request.state._t0 = time.time()
    a = _require_agent(request)
    rows = _attendance_export_rows(start, end, section)
    if (format or "").lower() == "csv":
        import io, csv
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["code", "name", "section_id", "date", "minutes", "in", "out", "anomaly"])
        for r in rows:
            w.writerow([r["code"], r["name"], r["section_id"], r["date"],
                        r["minutes"], r["in"], r["out"], r["anomaly"]])
        ms = int((time.time() - request.state._t0) * 1000)
        _log(a["id"], a.get("name", "?"), _client_ip(request), request.url.path, 200, ms)
        return PlainTextResponse(buf.getvalue(), media_type="text/csv; charset=utf-8",
                                 headers={"X-Response-Time": f"{ms}ms",
                                          "Content-Disposition": f'attachment; filename="attendance_{start}_{end}.csv"'})
    return _envelope(request, a, {"start": start, "end": end, "count": len(rows), "rows": rows}, max_age=60)


@router.get("/attendance-summary")
def agent_attendance_summary(request: Request, start: str, end: str,
                             section: int | None = None, format: str = "json"):
    """Per-employee summary over a range (≤92 days): days worked, total/overtime
    hours, absent days, attendance rate. `format=csv` for a download. Change #6."""
    request.state._t0 = time.time()
    a = _require_agent(request)
    rows = _attendance_summary_rows(start, end, section)
    if (format or "").lower() == "csv":
        import io, csv
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["code", "name", "section_id", "present_days", "absent_days",
                    "total_minutes", "total_hours_hhmm", "overtime_minutes", "overtime_hhmm", "attendance_rate_pct"])
        for r in rows:
            w.writerow([r["code"], r["name"], r["section_id"], r["present_days"], r["absent_days"],
                        r["total_minutes"], r["total_hours_hhmm"], r["overtime_minutes"], r["overtime_hhmm"], r["attendance_rate_pct"]])
        ms = int((time.time() - request.state._t0) * 1000)
        _log(a["id"], a.get("name", "?"), _client_ip(request), request.url.path, 200, ms)
        return PlainTextResponse(buf.getvalue(), media_type="text/csv; charset=utf-8",
                                 headers={"X-Response-Time": f"{ms}ms",
                                          "Content-Disposition": f'attachment; filename="attendance_summary_{start}_{end}.csv"'})
    totals = {"employees": len(rows),
              "total_minutes": sum(r["total_minutes"] for r in rows),
              "total_overtime_minutes": sum(r["overtime_minutes"] for r in rows)}
    return _envelope(request, a, {"start": start, "end": end, "count": len(rows), "totals": totals, "rows": rows}, max_age=60)


@router.get("/roster")
def agent_roster(request: Request, section: str = "all"):
    request.state._t0 = time.time()
    a = _require_agent(request)
    return _envelope(request, a, _proxy_json(f"/api/members/list?section={section}"), max_age=300)


@router.get("/dayoff")
def agent_dayoff(request: Request):
    request.state._t0 = time.time()
    a = _require_agent(request)
    return _envelope(request, a, _proxy_json("/api/dayoff/schedule"), max_age=120)


@router.get("/packs/{date}/history")
def agent_packs_history(request: Request, date: str):
    request.state._t0 = time.time()
    a = _require_agent(request)
    return _envelope(request, a, _proxy_json(f"/api/daily-packs/{date}/history"), max_age=0)


# ===========================================================================
#  REST — write endpoints (sync def → FastAPI threadpool; gated on write_enabled)
# ===========================================================================
@router.post("/packs")
def agent_set_packs(request: Request, payload: dict = Body(...)):
    request.state._t0 = time.time()
    a = _require_agent(request)
    _require_write(a)
    out = _proxy_write("POST", "/api/daily-packs", {
        "record_date": payload.get("record_date"),
        "number_of_packs": payload.get("number_of_packs"),
        "note": payload.get("note", ""),
    })
    return _envelope(request, a, out, max_age=0)


@router.post("/packs/bulk")
def agent_set_packs_bulk(request: Request, payload: dict = Body(...)):
    request.state._t0 = time.time()
    a = _require_agent(request)
    _require_write(a)
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise AgentAPIError(400, "bad_request", "entries must be a list")
    out = _proxy_write("POST", "/api/daily-packs/bulk", {"entries": entries})
    return _envelope(request, a, out, max_age=0)


@router.post("/temp-staff")
def agent_set_temp_staff(request: Request, payload: dict = Body(...)):
    request.state._t0 = time.time()
    a = _require_agent(request)
    _require_write(a)
    out = _proxy_write("POST", "/api/temp-staff", {
        "record_date": payload.get("record_date"),
        "rows": payload.get("rows", []),
    })
    return _envelope(request, a, out, max_age=0)


# ===========================================================================
#  REST — change-management (Part B). Agents see only their own requests.
# ===========================================================================
def _cr_guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except cr.ChangeRequestError as exc:
        raise AgentAPIError(exc.status,
                            "not_found" if exc.status == 404 else "bad_request",
                            exc.message)


@router.post("/requests")
def agent_submit_request(request: Request, payload: dict = Body(...)):
    request.state._t0 = time.time()
    a = _require_agent(request)
    row = _cr_guard(cr.create_request, a["id"], a.get("name"),
                    payload.get("title", ""), payload.get("body", ""),
                    payload.get("category", "change"))
    return _envelope(request, a, row, max_age=0)


@router.get("/requests")
def agent_list_requests(request: Request, status: str | None = None):
    request.state._t0 = time.time()
    a = _require_agent(request)
    return _envelope(request, a, _cr_guard(cr.list_requests, a["id"], status), max_age=0)


@router.get("/requests/{req_id}")
def agent_get_request(request: Request, req_id: int):
    request.state._t0 = time.time()
    a = _require_agent(request)
    row = cr.get_request(req_id, agent_id=a["id"])
    if not row:
        raise AgentAPIError(404, "not_found", "request not found")
    return _envelope(request, a, row, max_age=0)


@router.post("/requests/{req_id}/messages")
def agent_post_message(request: Request, req_id: int, payload: dict = Body(...)):
    request.state._t0 = time.time()
    a = _require_agent(request)
    _cr_guard(cr.add_message, req_id, "agent", payload.get("message", ""),
              "message", None, a["id"])
    return _envelope(request, a, cr.get_request(req_id, agent_id=a["id"]), max_age=0)


@router.post("/requests/{req_id}/feedback")
def agent_post_feedback(request: Request, req_id: int, payload: dict = Body(...)):
    request.state._t0 = time.time()
    a = _require_agent(request)
    row = _cr_guard(cr.add_feedback, req_id, a["id"],
                    payload.get("results", ""), payload.get("issues", ""),
                    payload.get("completion_status", "in_progress"))
    return _envelope(request, a, row, max_age=0)


# ===========================================================================
#  MCP — JSON-RPC 2.0 over plain HTTP (streamable-HTTP, request/response form)
# ===========================================================================
_TOOLS = [
    {"name": "get_production", "description": "Get the production + productivity snapshot for a date (defaults to latest). Use to read pack totals, section labor productivity, and the plan.",
     "inputSchema": {"type": "object", "properties": {"date": {"type": "string", "description": "YYYY-MM-DD, optional"}}}},
    {"name": "get_productivity", "description": "Get the labor-productivity series (packs/hour) for a period plus the prior period for comparison.",
     "inputSchema": {"type": "object", "properties": {"range": {"type": "string", "enum": ["day", "week", "month", "3month"]}, "end": {"type": "string", "description": "YYYY-MM-DD, optional"}}}},
    {"name": "get_packs", "description": "Get per-item produced-pack rows for one production date.",
     "inputSchema": {"type": "object", "properties": {"date": {"type": "string"}}, "required": ["date"]}},
    {"name": "get_attendance_range", "description": "Get ONE employee's daily attendance over a date range in a single call (minutes, in/out, anomaly per day + total). Use this for monthly/per-employee views instead of calling get_attendance once per day.",
     "inputSchema": {"type": "object", "properties": {"employee_code": {"type": "string"}, "start": {"type": "string", "description": "YYYY-MM-DD"}, "end": {"type": "string", "description": "YYYY-MM-DD"}, "section": {"type": "integer", "enum": [1, 2]}}, "required": ["employee_code", "start", "end"]}},
    {"name": "get_attendance_export", "description": "Export ALL employees' daily attendance over a date range (≤92 days) in ONE call — list of {code,name,section_id,date,minutes,in,out,anomaly}. Use for company-wide / multi-week pulls instead of many per-day calls.",
     "inputSchema": {"type": "object", "properties": {"start": {"type": "string", "description": "YYYY-MM-DD"}, "end": {"type": "string", "description": "YYYY-MM-DD"}, "section": {"type": "integer", "enum": [1, 2]}}, "required": ["start", "end"]}},
    {"name": "get_attendance_summary", "description": "Per-employee SUMMARY over a date range (month/range, ≤92 days): days worked, total hours, overtime (>8h/day), absent days, attendance rate. Use for monthly attendance / performance reports.",
     "inputSchema": {"type": "object", "properties": {"start": {"type": "string", "description": "YYYY-MM-DD"}, "end": {"type": "string", "description": "YYYY-MM-DD"}, "section": {"type": "integer", "enum": [1, 2]}}, "required": ["start", "end"]}},
    {"name": "get_attendance", "description": "Get per-employee attendance (in/out, worked hours) plus per-section and grand totals for a date.",
     "inputSchema": {"type": "object", "properties": {"date": {"type": "string"}, "section": {"type": "integer", "enum": [1, 2]}}, "required": ["date"]}},
    {"name": "get_roster", "description": "List the employee roster (read-only).",
     "inputSchema": {"type": "object", "properties": {"section": {"type": "string", "enum": ["all", "1", "2"]}}}},
    {"name": "get_dayoff_schedule", "description": "Read the current day-off schedule (read-only).",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "get_packs_history", "description": "Read the pack-count audit trail for a date — use to confirm a write you made landed.",
     "inputSchema": {"type": "object", "properties": {"date": {"type": "string"}}, "required": ["date"]}},
    {"name": "set_pack_count", "description": "Record or correct the produced-pack total for one date. Audit-logged. Requires write access.",
     "inputSchema": {"type": "object", "properties": {"record_date": {"type": "string"}, "number_of_packs": {"type": "integer"}, "note": {"type": "string"}}, "required": ["record_date", "number_of_packs"]}},
    {"name": "set_pack_counts_bulk", "description": "Upsert pack counts for several dates at once. Requires write access.",
     "inputSchema": {"type": "object", "properties": {"entries": {"type": "array", "items": {"type": "object"}}}, "required": ["entries"]}},
    {"name": "set_temp_staff", "description": "Replace the temp/Fullcast staff rows for one date. Requires write access.",
     "inputSchema": {"type": "object", "properties": {"record_date": {"type": "string"}, "rows": {"type": "array", "items": {"type": "object"}}}, "required": ["record_date", "rows"]}},
    {"name": "submit_change_request", "description": "Submit a new feature/system/change request for the admin to evaluate (feasibility, risk, timeline) and approve. Use when you need a capability the API does not yet provide.",
     "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}, "body": {"type": "string"}, "category": {"type": "string", "enum": ["feature", "system", "change", "bug"]}}, "required": ["title", "body"]}},
    {"name": "list_my_requests", "description": "List the change requests you have submitted, with their current status.",
     "inputSchema": {"type": "object", "properties": {"status": {"type": "string"}}}},
    {"name": "get_request", "description": "Get one of your change requests in full, including the conversation thread and the admin's evaluation/decision.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]}},
    {"name": "post_request_message", "description": "Post a message into the conversation thread of one of your change requests (e.g. to answer a needs_info).",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "integer"}, "message": {"type": "string"}}, "required": ["id", "message"]}},
    {"name": "post_request_feedback", "description": "Report implementation results/issues and completion status on one of your requests once it is in progress.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "integer"}, "results": {"type": "string"}, "issues": {"type": "string"}, "completion_status": {"type": "string", "enum": ["in_progress", "completed", "failed", "blocked"]}}, "required": ["id", "completion_status"]}},
]


def _mcp_call_tool(agent: dict, name: str, args: dict):
    """Dispatch a tool call (runs in a threadpool; may block on DB/HTTP)."""
    aid = agent["id"]
    if name == "get_production":
        return _proxy_json("/api/dashboard/snapshot" + (f"?date={args['date']}" if args.get("date") else ""))
    if name == "get_productivity":
        q = f"?range={args.get('range', 'month')}" + (f"&end={args['end']}" if args.get("end") else "")
        return _proxy_json("/api/productivity" + q)
    if name == "get_packs":
        return _proxy_json(f"/api/daily-packs/items/{args['date']}")
    if name == "get_attendance_range":
        return _attendance_range_data(args["employee_code"], args["start"], args["end"], args.get("section"))
    if name == "get_attendance_export":
        rows = _attendance_export_rows(args["start"], args["end"], args.get("section"))
        return {"start": args["start"], "end": args["end"], "count": len(rows), "rows": rows}
    if name == "get_attendance_summary":
        rows = _attendance_summary_rows(args["start"], args["end"], args.get("section"))
        return {"start": args["start"], "end": args["end"], "count": len(rows), "rows": rows}
    if name == "get_attendance":
        return _attendance_data(args["date"], args.get("section"))
    if name == "get_roster":
        return _proxy_json(f"/api/members/list?section={args.get('section', 'all')}")
    if name == "get_dayoff_schedule":
        return _proxy_json("/api/dayoff/schedule")
    if name == "get_packs_history":
        return _proxy_json(f"/api/daily-packs/{args['date']}/history")
    if name == "set_pack_count":
        _require_write(agent)
        return _proxy_write("POST", "/api/daily-packs", {
            "record_date": args["record_date"], "number_of_packs": args["number_of_packs"],
            "note": args.get("note", "")})
    if name == "set_pack_counts_bulk":
        _require_write(agent)
        return _proxy_write("POST", "/api/daily-packs/bulk", {"entries": args["entries"]})
    if name == "set_temp_staff":
        _require_write(agent)
        return _proxy_write("POST", "/api/temp-staff", {
            "record_date": args["record_date"], "rows": args["rows"]})
    if name == "submit_change_request":
        return _cr_guard(cr.create_request, aid, agent.get("name"),
                         args.get("title", ""), args.get("body", ""), args.get("category", "change"))
    if name == "list_my_requests":
        return _cr_guard(cr.list_requests, aid, args.get("status"))
    if name == "get_request":
        row = cr.get_request(int(args["id"]), agent_id=aid)
        if not row:
            raise AgentAPIError(404, "not_found", "request not found")
        return row
    if name == "post_request_message":
        _cr_guard(cr.add_message, int(args["id"]), "agent", args.get("message", ""), "message", None, aid)
        return cr.get_request(int(args["id"]), agent_id=aid)
    if name == "post_request_feedback":
        return _cr_guard(cr.add_feedback, int(args["id"]), aid,
                         args.get("results", ""), args.get("issues", ""),
                         args.get("completion_status", "in_progress"))
    raise AgentAPIError(400, "unknown_tool", f"unknown tool: {name}")


def _jrpc_err(rid, code, message):
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


async def mcp_post(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return SJSONResponse(_jrpc_err(None, -32700, "Parse error"), status_code=400)
    rid = payload.get("id") if isinstance(payload, dict) else None
    method = payload.get("method") if isinstance(payload, dict) else None
    # Auth on every call (the bearer header rides every HTTP request).
    # No token → 401 + RFC9728 WWW-Authenticate so the client starts OAuth discovery.
    _wwwauth = {"WWW-Authenticate": f'Bearer resource_metadata="{_mcp_base(request)}/.well-known/oauth-protected-resource"'}
    if not _extract_token(request):
        return SJSONResponse(_jrpc_err(rid, -32001, "Authentication required"),
                             status_code=401, headers=_wwwauth)
    try:
        agent = _require_agent(request)
    except AgentAPIError as exc:
        headers = _wwwauth if exc.status == 401 else {}
        return SJSONResponse(_jrpc_err(rid, -32001, exc.message), status_code=exc.status, headers=headers)
    if method == "initialize":
        return SJSONResponse({"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": "2025-06-18",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "genba-fms-agent", "version": API_VERSION}}})
    if method in ("notifications/initialized", "initialized", "notifications/cancelled"):
        return SResponse(status_code=202)
    if method == "tools/list":
        return SJSONResponse({"jsonrpc": "2.0", "id": rid, "result": {"tools": _TOOLS}})
    if method == "tools/call":
        params = payload.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        t0 = time.time()
        ip = _client_ip(request)
        try:
            result = await run_in_threadpool(_mcp_call_tool, agent, name, args)
            text = json.dumps(result, ensure_ascii=False, default=str)
            _log(agent["id"], agent.get("name", "?"), ip, f"/mcp:{name}", 200, int((time.time() - t0) * 1000))
            return SJSONResponse({"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": text}], "isError": False}})
        except AgentAPIError as exc:
            _log(agent["id"], agent.get("name", "?"), ip, f"/mcp:{name}", exc.status, int((time.time() - t0) * 1000))
            return SJSONResponse({"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": f"{exc.code}: {exc.message}"}], "isError": True}})
        except Exception as exc:
            _log(agent["id"], agent.get("name", "?"), ip, f"/mcp:{name}", 500, int((time.time() - t0) * 1000))
            return SJSONResponse({"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": str(exc)}], "isError": True}})
    return SJSONResponse(_jrpc_err(rid, -32601, f"Method not found: {method}"))


async def mcp_get(request: Request):
    # No server→client SSE stream; tool calls are request/response. Unauthenticated
    # GET returns 401 + discovery header (helps clients that probe with GET first).
    if not _extract_token(request):
        return SResponse(status_code=401, headers={
            "WWW-Authenticate": f'Bearer resource_metadata="{_mcp_base(request)}/.well-known/oauth-protected-resource"'})
    return SResponse(status_code=405)


# ===========================================================================
#  Admin helpers (called by main.py's admin-gated endpoints)
# ===========================================================================
def agent_status() -> dict:
    cfg = _load()
    out = []
    for a in cfg.get("agents", []):
        st = _STAT.get(a["id"], {})
        out.append({
            "id": a["id"], "name": a.get("name"),
            "disabled": bool(a.get("disabled")),
            "write_enabled": bool(a.get("write_enabled", True)),
            "rate_per_min": a.get("rate_per_min", 60),
            "ip_allowlist": a.get("ip_allowlist") or [],
            "created_at": a.get("created_at"),
            "calls": st.get("calls", 0),
            "last_seen": st.get("last_seen"), "last_ip": st.get("last_ip"),
            "token_tail": ("…" + str(a.get("token", ""))[-6:]) if a.get("token") else "",
        })
    return {"enabled": bool(cfg.get("enabled")), "count": len(out),
            "api_version": API_VERSION, "agents": out}


def agent_set_enabled(enabled: bool) -> dict:
    cfg = _load()
    cfg["enabled"] = bool(enabled)
    _save(cfg)
    print(f"[AGENT_API] enabled={cfg['enabled']}")
    return agent_status()


def agent_add(name: str, rate_per_min: int = 60, ip_allowlist: list | None = None,
              write_enabled: bool = True) -> dict:
    cfg = _load()
    aid = "a_" + secrets.token_hex(4)
    token = "at_" + secrets.token_urlsafe(28)
    cfg.setdefault("agents", []).append({
        "id": aid, "name": (name or "agent").strip()[:80], "token": token,
        "rate_per_min": int(rate_per_min or 60),
        "ip_allowlist": [s.strip() for s in (ip_allowlist or []) if s.strip()],
        "disabled": False, "write_enabled": bool(write_enabled),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    })
    _save(cfg)
    return {"ok": True, "id": aid, "name": name, "token": token}


def agent_update(aid: str, disabled: bool | None = None, rate_per_min: int | None = None,
                 ip_allowlist: list | None = None, write_enabled: bool | None = None) -> dict:
    cfg = _load()
    for a in cfg.get("agents", []):
        if a["id"] == aid:
            if disabled is not None:
                a["disabled"] = bool(disabled)
            if rate_per_min is not None:
                a["rate_per_min"] = int(rate_per_min)
            if write_enabled is not None:
                a["write_enabled"] = bool(write_enabled)
            if ip_allowlist is not None:
                a["ip_allowlist"] = [s.strip() for s in ip_allowlist if s.strip()]
            _save(cfg)
            return {"ok": True}
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="agent not found")


def agent_revoke(aid: str) -> dict:
    cfg = _load()
    before = len(cfg.get("agents", []))
    cfg["agents"] = [a for a in cfg.get("agents", []) if a["id"] != aid]
    _save(cfg)
    _RT.pop(aid, None)
    _STAT.pop(aid, None)
    return {"ok": True, "removed": before - len(cfg["agents"])}


def agent_log_tail(limit: int = 100) -> dict:
    limit = max(1, min(int(limit or 100), 1000))
    items, size = [], 0
    if AGENT_LOG_PATH.exists():
        try:
            size = AGENT_LOG_PATH.stat().st_size
            with AGENT_LOG_PATH.open("r", encoding="utf-8") as fh:
                tail = fh.readlines()[-limit:]
            for raw in tail:
                raw = raw.strip()
                if raw:
                    try:
                        items.append(json.loads(raw))
                    except Exception:
                        pass
        except Exception as exc:
            return {"path": str(AGENT_LOG_PATH), "error": str(exc), "items": []}
    return {"path": str(AGENT_LOG_PATH), "file_size_bytes": size,
            "status": agent_status(), "count": len(items),
            "items": list(reversed(items))}
