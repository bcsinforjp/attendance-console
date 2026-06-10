"""
change_requests.py — Agent Change-Management ledger (Part B).

A small, self-contained workflow store: external agents submit feature/system
requests; an admin evaluates (feasibility / risk / timeline) and decides; a human
implements; the agent reports feedback. Everything is tracked so the admin panel
can show "all conversations and commitments in one place".

Decoupled from main.py on purpose (own DB connection from the same env vars) to
avoid a circular import (main → agent_api → change_requests). Mirrors the
independence philosophy of partner_api.py.

Tables (created idempotently by ensure_tables(), also safe to add to init_db()):
  agent_change_requests  — one row per request + its evaluation/decision state
  agent_change_messages  — the conversation thread + feedback entries

Lifecycle:
  submitted -> under_review -> (approved | rejected | needs_info)
            -> in_progress -> (completed | failed)
"""
from __future__ import annotations

import os
from datetime import datetime

import psycopg2
import psycopg2.extras

_DB = dict(
    host=os.getenv("ATTENDANCE_DB_HOST", "127.0.0.1"),
    port=int(os.getenv("ATTENDANCE_DB_PORT", "5432")),
    dbname=os.getenv("ATTENDANCE_DB_NAME", "attendance_db"),
    user=os.getenv("ATTENDANCE_DB_USER", "attendance"),
    password=os.getenv("ATTENDANCE_DB_PASSWORD", "attendance2026"),
)

VALID_CATEGORY = {"feature", "system", "change", "bug"}
VALID_RISK = {"low", "med", "high"}
VALID_DECISION = {"approved", "rejected", "needs_info"}
VALID_PROGRESS = {"in_progress", "completed", "failed"}
# completion_status an agent may report via feedback
VALID_COMPLETION = {"in_progress", "completed", "failed", "blocked"}


class ChangeRequestError(Exception):
    """Raised for not-found / invalid-input / ownership violations.
    `status` is an HTTP-ish hint the caller maps onto its own error envelope."""
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(message)


def _conn():
    return psycopg2.connect(**_DB)


def ensure_tables() -> None:
    """Idempotent — safe to call on every startup."""
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS agent_change_requests (
                    id                SERIAL PRIMARY KEY,
                    agent_id          TEXT NOT NULL,
                    agent_name        TEXT,
                    title             TEXT NOT NULL,
                    body              TEXT,
                    category          TEXT NOT NULL DEFAULT 'change',
                    status            TEXT NOT NULL DEFAULT 'submitted',
                    feasible          BOOLEAN,
                    risk_level        TEXT,
                    timeline_estimate TEXT,
                    eval_notes        TEXT,
                    evaluated_by      TEXT,
                    evaluated_at      TIMESTAMP,
                    decision_notes    TEXT,
                    decided_by        TEXT,
                    decided_at        TIMESTAMP,
                    created_at        TIMESTAMP NOT NULL DEFAULT now(),
                    updated_at        TIMESTAMP NOT NULL DEFAULT now()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS agent_change_messages (
                    id         SERIAL PRIMARY KEY,
                    request_id INTEGER NOT NULL
                               REFERENCES agent_change_requests(id) ON DELETE CASCADE,
                    author     TEXT NOT NULL,
                    kind       TEXT NOT NULL DEFAULT 'message',
                    body       TEXT,
                    meta       JSONB,
                    created_at TIMESTAMP NOT NULL DEFAULT now()
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_acr_agent  ON agent_change_requests(agent_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_acr_status ON agent_change_requests(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_acm_req    ON agent_change_messages(request_id)")
        c.commit()


# ---- serialization ---------------------------------------------------------
def _ser(row: dict) -> dict:
    out = dict(row)
    for k, v in out.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat(timespec="seconds")
    return out


# ---- writes ----------------------------------------------------------------
def create_request(agent_id: str, agent_name: str, title: str,
                   body: str = "", category: str = "change") -> dict:
    title = (title or "").strip()
    if not title:
        raise ChangeRequestError(400, "title is required")
    category = category if category in VALID_CATEGORY else "change"
    with _conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO agent_change_requests (agent_id, agent_name, title, body, category)
                VALUES (%s, %s, %s, %s, %s) RETURNING *
            """, (agent_id, agent_name, title[:300], (body or "")[:8000], category))
            row = cur.fetchone()
            cur.execute("""
                INSERT INTO agent_change_messages (request_id, author, kind, body)
                VALUES (%s, 'agent', 'message', %s)
            """, (row["id"], (body or "")[:8000]))
        c.commit()
    return _ser(row)


def _touch_and_fetch(cur, req_id: int) -> dict:
    cur.execute("UPDATE agent_change_requests SET updated_at = now() WHERE id = %s RETURNING *", (req_id,))
    row = cur.fetchone()
    if not row:
        raise ChangeRequestError(404, "request not found")
    return _ser(row)


def add_message(req_id: int, author: str, body: str, kind: str = "message",
                meta: dict | None = None, agent_id: str | None = None) -> dict:
    with _conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            _assert_exists(cur, req_id, agent_id)
            cur.execute("""
                INSERT INTO agent_change_messages (request_id, author, kind, body, meta)
                VALUES (%s, %s, %s, %s, %s) RETURNING *
            """, (req_id, author, kind, (body or "")[:8000],
                  psycopg2.extras.Json(meta) if meta is not None else None))
            msg = cur.fetchone()
            _touch_and_fetch(cur, req_id)
        c.commit()
    return _ser(msg)


def add_feedback(req_id: int, agent_id: str, results: str = "", issues: str = "",
                 completion_status: str = "in_progress") -> dict:
    completion_status = completion_status if completion_status in VALID_COMPLETION else "in_progress"
    body_parts = []
    if results:
        body_parts.append(f"Results: {results}")
    if issues:
        body_parts.append(f"Issues: {issues}")
    body_parts.append(f"Status: {completion_status}")
    body = "\n".join(body_parts)
    meta = {"results": results, "issues": issues, "completion_status": completion_status}
    with _conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT status FROM agent_change_requests WHERE id = %s AND agent_id = %s",
                        (req_id, agent_id))
            r = cur.fetchone()
            if not r:
                raise ChangeRequestError(404, "request not found")
            cur.execute("""
                INSERT INTO agent_change_messages (request_id, author, kind, body, meta)
                VALUES (%s, 'agent', 'feedback', %s, %s)
            """, (req_id, body, psycopg2.extras.Json(meta)))
            # Agent feedback may advance an in-progress request to its terminal state.
            if completion_status in ("completed", "failed") and r["status"] == "in_progress":
                cur.execute("UPDATE agent_change_requests SET status = %s, updated_at = now() WHERE id = %s",
                            (completion_status, req_id))
            else:
                cur.execute("UPDATE agent_change_requests SET updated_at = now() WHERE id = %s", (req_id,))
        c.commit()
    return get_request(req_id, agent_id=agent_id)


def evaluate(req_id: int, feasible, risk_level: str, timeline_estimate: str,
             notes: str, by: str = "admin") -> dict:
    if risk_level and risk_level not in VALID_RISK:
        raise ChangeRequestError(400, "risk_level must be low|med|high")
    feas = None if feasible is None else bool(feasible)
    with _conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            _assert_exists(cur, req_id)
            cur.execute("""
                UPDATE agent_change_requests
                   SET feasible = %s, risk_level = %s, timeline_estimate = %s,
                       eval_notes = %s, evaluated_by = %s, evaluated_at = now(),
                       status = CASE WHEN status = 'submitted' THEN 'under_review' ELSE status END,
                       updated_at = now()
                 WHERE id = %s
            """, (feas, (risk_level or None), (timeline_estimate or None),
                  (notes or None), by, req_id))
            cur.execute("""
                INSERT INTO agent_change_messages (request_id, author, kind, body, meta)
                VALUES (%s, 'admin', 'evaluation', %s, %s)
            """, (req_id,
                  f"Evaluation — feasible={feas}, risk={risk_level}, timeline={timeline_estimate}\n{notes or ''}".strip(),
                  psycopg2.extras.Json({"feasible": feas, "risk_level": risk_level,
                                        "timeline_estimate": timeline_estimate})))
        c.commit()
    return get_request(req_id)


def decide(req_id: int, decision: str, notes: str = "", by: str = "admin") -> dict:
    if decision not in VALID_DECISION:
        raise ChangeRequestError(400, "decision must be approved|rejected|needs_info")
    with _conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            _assert_exists(cur, req_id)
            cur.execute("""
                UPDATE agent_change_requests
                   SET status = %s, decision_notes = %s, decided_by = %s,
                       decided_at = now(), updated_at = now()
                 WHERE id = %s
            """, (decision, (notes or None), by, req_id))
            cur.execute("""
                INSERT INTO agent_change_messages (request_id, author, kind, body)
                VALUES (%s, 'admin', 'status_change', %s)
            """, (req_id, f"Decision: {decision}\n{notes or ''}".strip()))
        c.commit()
    return get_request(req_id)


def set_status(req_id: int, status: str, by: str = "admin") -> dict:
    if status not in VALID_PROGRESS:
        raise ChangeRequestError(400, "status must be in_progress|completed|failed")
    with _conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            _assert_exists(cur, req_id)
            cur.execute("UPDATE agent_change_requests SET status = %s, updated_at = now() WHERE id = %s",
                        (status, req_id))
            cur.execute("""
                INSERT INTO agent_change_messages (request_id, author, kind, body)
                VALUES (%s, 'admin', 'status_change', %s)
            """, (req_id, f"Status → {status}"))
        c.commit()
    return get_request(req_id)


# ---- reads -----------------------------------------------------------------
def _assert_exists(cur, req_id: int, agent_id: str | None = None) -> None:
    if agent_id is None:
        cur.execute("SELECT 1 FROM agent_change_requests WHERE id = %s", (req_id,))
    else:
        cur.execute("SELECT 1 FROM agent_change_requests WHERE id = %s AND agent_id = %s",
                    (req_id, agent_id))
    if not cur.fetchone():
        raise ChangeRequestError(404, "request not found")


def list_requests(agent_id: str | None = None, status: str | None = None,
                  limit: int = 100) -> list:
    limit = max(1, min(int(limit or 100), 500))
    where = []
    args: list = []
    if agent_id:
        where.append("agent_id = %s")
        args.append(agent_id)
    if status:
        where.append("status = %s")
        args.append(status)
    sql = "SELECT * FROM agent_change_requests"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY updated_at DESC LIMIT %s"
    args.append(limit)
    with _conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, tuple(args))
            return [_ser(r) for r in cur.fetchall()]


def get_request(req_id: int, agent_id: str | None = None) -> dict | None:
    with _conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if agent_id:
                cur.execute("SELECT * FROM agent_change_requests WHERE id = %s AND agent_id = %s",
                            (req_id, agent_id))
            else:
                cur.execute("SELECT * FROM agent_change_requests WHERE id = %s", (req_id,))
            row = cur.fetchone()
            if not row:
                return None
            cur.execute("""
                SELECT id, author, kind, body, meta, created_at
                  FROM agent_change_messages WHERE request_id = %s ORDER BY id ASC
            """, (req_id,))
            msgs = [_ser(m) for m in cur.fetchall()]
    out = _ser(row)
    out["messages"] = msgs
    return out


def status_counts() -> dict:
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("SELECT status, COUNT(*) FROM agent_change_requests GROUP BY status")
            return {row[0]: int(row[1]) for row in cur.fetchall()}
