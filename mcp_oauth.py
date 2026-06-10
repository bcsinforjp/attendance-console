"""
mcp_oauth.py — minimal OAuth 2.1 Authorization Server for the MCP connector.

Implements just enough of the MCP authorization spec so Claude's (and other
clients') "Add custom connector" flow can register and sign in to /mcp without a
manually pasted token:

  * RFC 9728 protected-resource metadata  (/.well-known/oauth-protected-resource)
  * RFC 8414 authorization-server metadata (/.well-known/oauth-authorization-server)
  * RFC 7591 dynamic client registration   (POST /oauth/register)
  * OAuth 2.1 authorization code + PKCE S256 (/oauth/authorize, /oauth/token)

Approval is gated by the GENBA FMS **admin password**. A successful sign-in mints
an access token bound to a managed agent record (so it shows up in /admin → Agent
API and is revocable / rate-limited like any other agent). Access tokens are also
accepted by the REST API, since agent_api._require_agent resolves them.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Request, Form
from fastapi.responses import (JSONResponse, HTMLResponse, RedirectResponse,
                               PlainTextResponse)

import agent_api

BASE_DIR = Path(__file__).resolve().parent
STORE_PATH = BASE_DIR / "mcp_oauth.json"
ADMIN_CONFIG_PATH = BASE_DIR / "admin_config.json"

ACCESS_TTL = 30 * 24 * 3600   # 30 days
CODE_TTL = 600                # 10 minutes

router = APIRouter(tags=["mcp-oauth"])

_clients: dict = {}   # client_id -> {redirect_uris, client_name, created_at}
_tokens: dict = {}    # access_token -> {agent_id, client_id, expires_at, refresh_token}
_codes: dict = {}     # code -> {client_id, redirect_uri, code_challenge, agent_id, expires_at}  (memory only)


def _load_store() -> None:
    global _clients, _tokens
    try:
        if STORE_PATH.exists():
            d = json.loads(STORE_PATH.read_text(encoding="utf-8"))
            _clients = d.get("clients", {}) or {}
            _tokens = d.get("tokens", {}) or {}
    except Exception as exc:
        print(f"[MCP_OAUTH] load failed: {exc}")


def _save_store() -> None:
    try:
        tmp = STORE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"clients": _clients, "tokens": _tokens},
                                  ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(STORE_PATH)
        os.chmod(STORE_PATH, 0o600)
    except Exception as exc:
        print(f"[MCP_OAUTH] save failed: {exc}")


_load_store()


def _admin_password() -> str:
    try:
        return json.loads(ADMIN_CONFIG_PATH.read_text(encoding="utf-8")).get("password", "")
    except Exception:
        return ""


def _connect_password() -> str:
    """A dedicated approval password for AI connectors (separate from the admin
    console password) — set as `mcp_connect_password` in admin_config.json."""
    try:
        return json.loads(ADMIN_CONFIG_PATH.read_text(encoding="utf-8")).get("mcp_connect_password", "")
    except Exception:
        return ""


def _base(request: Request) -> str:
    host = (request.headers.get("x-forwarded-host")
            or request.headers.get("host") or "link.genbafms.com")
    proto = "http" if host.startswith(("127.", "localhost")) else "https"
    return f"{proto}://{host}"


def _esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def resolve_token(token: str):
    """Called by agent_api._require_agent for non-static bearer tokens.
    Returns the bound agent_id or None."""
    rec = _tokens.get(token)
    if not rec:
        return None
    if rec["expires_at"] < time.time():
        _tokens.pop(token, None)
        _save_store()
        return None
    return rec["agent_id"]


# ---- discovery metadata ----------------------------------------------------
@router.get("/.well-known/oauth-protected-resource")
@router.get("/.well-known/oauth-protected-resource/mcp")
def protected_resource(request: Request):
    b = _base(request)
    return JSONResponse({"resource": f"{b}/mcp", "authorization_servers": [b],
                         "bearer_methods_supported": ["header"]})


def _as_meta(request: Request) -> dict:
    b = _base(request)
    return {
        "issuer": b,
        "authorization_endpoint": f"{b}/oauth/authorize",
        "token_endpoint": f"{b}/oauth/token",
        "registration_endpoint": f"{b}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["mcp"],
    }


@router.get("/.well-known/oauth-authorization-server")
@router.get("/.well-known/oauth-authorization-server/mcp")
def as_metadata(request: Request):
    return JSONResponse(_as_meta(request))


@router.get("/.well-known/openid-configuration")
def oidc(request: Request):
    return JSONResponse(_as_meta(request))


# ---- dynamic client registration (RFC 7591) --------------------------------
@router.post("/oauth/register")
async def register(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    cid = "mcpc_" + secrets.token_hex(8)
    redirect_uris = body.get("redirect_uris") or []
    _clients[cid] = {"redirect_uris": redirect_uris,
                     "client_name": (body.get("client_name") or "MCP Client")[:80],
                     "created_at": datetime.now().isoformat(timespec="seconds")}
    _save_store()
    return JSONResponse({
        "client_id": cid,
        "token_endpoint_auth_method": "none",
        "redirect_uris": redirect_uris,
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "client_id_issued_at": int(time.time()),
    }, status_code=201)


# ---- authorization endpoint ------------------------------------------------
_AUTHZ_FIELDS = ["client_id", "redirect_uri", "state", "code_challenge",
                 "code_challenge_method", "scope", "resource", "response_type"]


@router.get("/oauth/authorize")
def authorize_get(request: Request):
    q = dict(request.query_params)
    fields = {k: q.get(k, "") for k in _AUTHZ_FIELDS}
    client = _clients.get(fields["client_id"])
    cname = client["client_name"] if client else (fields["client_id"] or "An application")
    inputs = "".join(f'<input type="hidden" name="{k}" value="{_esc(v)}">'
                     for k, v in fields.items())
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Authorize · GENBA FMS</title>
<style>
 body{{font-family:system-ui,Segoe UI,sans-serif;background:#0a0a0f;color:#e8e8ee;
   display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}}
 .card{{background:#15151f;border:1px solid #2a2a3a;border-radius:12px;padding:2rem;max-width:400px;box-shadow:0 10px 40px rgba(0,0,0,.5)}}
 h2{{color:#00e5ff;margin:0 0 .8rem}} p{{line-height:1.5;font-size:.92rem;color:#c7c7d2}}
 b{{color:#fff}} input[type=password]{{width:100%;box-sizing:border-box;padding:.6rem;margin:.6rem 0;
   background:#0a0a0f;border:1px solid #3a3a4a;color:#fff;border-radius:6px;font-size:1rem}}
 button{{width:100%;padding:.7rem;background:#00e5ff;color:#001016;border:0;border-radius:6px;font-weight:700;cursor:pointer;font-size:1rem}}
 .muted{{color:#7a7a8a;font-size:.78rem;margin-top:1rem}}
</style></head><body>
<form class="card" method="post" action="/oauth/authorize">
 <h2>Connect to GENBA FMS</h2>
 <p><b>{_esc(cname)}</b> is requesting access to read &amp; write factory data and submit change requests, acting as an agent.</p>
 {inputs}
 <p>Enter the <b>connector password</b> to approve / 接続パスワードを入力:</p>
 <input type="password" name="admin_password" placeholder="connector password" autofocus required>
 <button type="submit">Approve &amp; Connect</button>
 <div class="muted">You can revoke this access anytime in /admin → Agent API.</div>
</form></body></html>"""
    return HTMLResponse(html)


@router.post("/oauth/authorize")
async def authorize_post(request: Request, admin_password: str = Form("")):
    form = dict(await request.form())
    pw = admin_password or ""
    ap, cp = _admin_password(), _connect_password()
    ok = (ap and secrets.compare_digest(ap, pw)) or (cp and secrets.compare_digest(cp, pw))
    if not ok:
        return HTMLResponse(
            "<p style='font-family:system-ui;color:#b00'>Wrong password. "
            "<a href='javascript:history.back()'>Go back</a></p>", status_code=401)
    client_id = form.get("client_id", "")
    redirect_uri = form.get("redirect_uri", "")
    client = _clients.get(client_id)
    if not client:
        return PlainTextResponse("unknown client_id", status_code=400)
    allowed = client.get("redirect_uris") or []
    if allowed and redirect_uri not in allowed:
        return PlainTextResponse("redirect_uri not registered for this client", status_code=400)
    if not redirect_uri.startswith(("https://", "http://")):
        return PlainTextResponse("invalid redirect_uri", status_code=400)
    # Bind to a managed agent (created on first authorize for this client).
    agent = agent_api.ensure_oauth_agent("a_oauth_" + client_id[-8:],
                                         client.get("client_name", "Claude connector"))
    code = "code_" + secrets.token_urlsafe(24)
    _codes[code] = {"client_id": client_id, "redirect_uri": redirect_uri,
                    "code_challenge": form.get("code_challenge", ""),
                    "agent_id": agent["id"], "expires_at": time.time() + CODE_TTL}
    params = {"code": code}
    if form.get("state"):
        params["state"] = form["state"]
    sep = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(redirect_uri + sep + urlencode(params), status_code=302)


# ---- token endpoint --------------------------------------------------------
def _issue(agent_id: str, client_id: str):
    at = "mat_" + secrets.token_urlsafe(32)
    rt = "mrt_" + secrets.token_urlsafe(32)
    _tokens[at] = {"agent_id": agent_id, "client_id": client_id,
                   "expires_at": time.time() + ACCESS_TTL, "refresh_token": rt}
    _save_store()
    return JSONResponse({"access_token": at, "token_type": "Bearer",
                         "expires_in": ACCESS_TTL, "refresh_token": rt, "scope": "mcp"})


@router.post("/oauth/token")
async def token(request: Request):
    form = dict(await request.form())
    gt = form.get("grant_type")
    if gt == "authorization_code":
        rec = _codes.pop(form.get("code", ""), None)
        if not rec or rec["expires_at"] < time.time():
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        if rec["redirect_uri"] != form.get("redirect_uri", ""):
            return JSONResponse({"error": "invalid_grant",
                                 "error_description": "redirect_uri mismatch"}, status_code=400)
        if rec.get("code_challenge"):
            cv = form.get("code_verifier", "")
            calc = base64.urlsafe_b64encode(hashlib.sha256(cv.encode()).digest()).decode().rstrip("=")
            if not secrets.compare_digest(calc, rec["code_challenge"]):
                return JSONResponse({"error": "invalid_grant",
                                     "error_description": "PKCE verification failed"}, status_code=400)
        return _issue(rec["agent_id"], rec["client_id"])
    if gt == "refresh_token":
        rt = form.get("refresh_token", "")
        for at, t in list(_tokens.items()):
            if t.get("refresh_token") == rt:
                _tokens.pop(at, None)
                return _issue(t["agent_id"], t["client_id"])
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)
