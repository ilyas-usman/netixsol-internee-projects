"""Week 7 Day 4 — Task 5: CRM storage.

Own SQLite file (crm.db) — does not touch day3_memory.db or appointments.db.
Appointment HISTORY itself still lives in appointment_store.appointments
(the source of truth); this module only adds the pieces that were missing:
client identity + preferences, a running transcript log, and follow-up
reminders. get_client_profile() below is what stitches all four together
for a single "CRM view" of one client.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import date, datetime, timezone

from crm_config import CRM_DB, PREFERENCE_SLOT_KEYS

_LOCK = threading.Lock()


def _conn():
    c = sqlite3.connect(CRM_DB, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _LOCK:
        c = _conn()
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS clients (
                phone TEXT PRIMARY KEY,
                name TEXT,
                email TEXT,
                preferences_json TEXT NOT NULL DEFAULT '{}',
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS session_links (
                session_id TEXT PRIMARY KEY,
                client_phone TEXT NOT NULL,
                linked_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS transcripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                client_phone TEXT,
                channel TEXT NOT NULL DEFAULT 'chat',
                role TEXT NOT NULL,
                text TEXT NOT NULL,
                meta_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_transcripts_session ON transcripts(session_id);
            CREATE INDEX IF NOT EXISTS idx_transcripts_phone ON transcripts(client_phone);

            CREATE TABLE IF NOT EXISTS reminders (
                id TEXT PRIMARY KEY,
                client_phone TEXT,
                session_id TEXT,
                appointment_id TEXT,
                due_date TEXT NOT NULL,
                note TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_by TEXT NOT NULL DEFAULT 'system',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_reminders_phone ON reminders(client_phone);
            CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(status, due_date);
            """
        )
        c.commit()
        c.close()


def _now():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Clients & preferences
# ---------------------------------------------------------------------------
def upsert_client(phone: str, name: str | None = None, email: str | None = None) -> dict:
    if not phone:
        return {}
    with _LOCK:
        c = _conn()
        row = c.execute("SELECT * FROM clients WHERE phone=?", (phone,)).fetchone()
        now = _now()
        if row:
            c.execute(
                """
                UPDATE clients SET
                    name = COALESCE(?, name),
                    email = COALESCE(?, email),
                    last_seen = ?
                WHERE phone=?
                """,
                (name, email, now, phone),
            )
        else:
            c.execute(
                """
                INSERT INTO clients (phone, name, email, preferences_json, first_seen, last_seen)
                VALUES (?,?,?,?,?,?)
                """,
                (phone, name, email, "{}", now, now),
            )
        c.commit()
        result = c.execute("SELECT * FROM clients WHERE phone=?", (phone,)).fetchone()
        c.close()
    return dict(result) if result else {}


def merge_preferences(phone: str, slots: dict):
    if not phone or not slots:
        return
    relevant = {k: v for k, v in slots.items() if k in PREFERENCE_SLOT_KEYS and v not in (None, "")}
    if not relevant:
        return
    with _LOCK:
        c = _conn()
        row = c.execute("SELECT preferences_json FROM clients WHERE phone=?", (phone,)).fetchone()
        current = json.loads(row["preferences_json"]) if row else {}
        current.update(relevant)
        if row:
            c.execute(
                "UPDATE clients SET preferences_json=?, last_seen=? WHERE phone=?",
                (json.dumps(current, ensure_ascii=False), _now(), phone),
            )
        else:
            now = _now()
            c.execute(
                "INSERT INTO clients (phone, name, email, preferences_json, first_seen, last_seen) VALUES (?,?,?,?,?,?)",
                (phone, None, None, json.dumps(current, ensure_ascii=False), now, now),
            )
        c.commit()
        c.close()


def get_client(phone: str) -> dict | None:
    if not phone:
        return None
    c = _conn()
    row = c.execute("SELECT * FROM clients WHERE phone=?", (phone,)).fetchone()
    c.close()
    if not row:
        return None
    d = dict(row)
    d["preferences"] = json.loads(d.pop("preferences_json") or "{}")
    return d


def list_clients(limit: int = 100) -> list[dict]:
    c = _conn()
    rows = c.execute("SELECT * FROM clients ORDER BY last_seen DESC LIMIT ?", (limit,)).fetchall()
    c.close()
    out = []
    for row in rows:
        d = dict(row)
        d["preferences"] = json.loads(d.pop("preferences_json") or "{}")
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Session <-> client linking + transcripts
# ---------------------------------------------------------------------------
def link_session(session_id: str, phone: str):
    """Associate a session with a client phone, and backfill any transcript
    rows already logged for this session before the phone was known."""
    if not session_id or not phone:
        return
    with _LOCK:
        c = _conn()
        c.execute(
            """
            INSERT INTO session_links(session_id, client_phone, linked_at)
            VALUES (?,?,?)
            ON CONFLICT(session_id) DO UPDATE SET client_phone=excluded.client_phone, linked_at=excluded.linked_at
            """,
            (session_id, phone, _now()),
        )
        c.execute(
            "UPDATE transcripts SET client_phone=? WHERE session_id=? AND (client_phone IS NULL OR client_phone='')",
            (phone, session_id),
        )
        c.commit()
        c.close()


def get_phone_for_session(session_id: str) -> str | None:
    if not session_id:
        return None
    c = _conn()
    row = c.execute("SELECT client_phone FROM session_links WHERE session_id=?", (session_id,)).fetchone()
    c.close()
    return row["client_phone"] if row else None


def log_transcript(session_id: str, role: str, text: str, channel: str = "chat", meta: dict | None = None):
    phone = get_phone_for_session(session_id)
    with _LOCK:
        c = _conn()
        c.execute(
            """
            INSERT INTO transcripts (session_id, client_phone, channel, role, text, meta_json, created_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (session_id, phone, channel, role, text, json.dumps(meta or {}, ensure_ascii=False), _now()),
        )
        c.commit()
        c.close()


def get_transcripts(session_id: str | None = None, phone: str | None = None, limit: int = 50) -> list[dict]:
    c = _conn()
    if session_id:
        rows = c.execute(
            "SELECT * FROM transcripts WHERE session_id=? ORDER BY id ASC LIMIT ?", (session_id, limit)
        ).fetchall()
    elif phone:
        rows = c.execute(
            "SELECT * FROM transcripts WHERE client_phone=? ORDER BY id DESC LIMIT ?", (phone, limit)
        ).fetchall()
    else:
        rows = c.execute("SELECT * FROM transcripts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    c.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Follow-up reminders
# ---------------------------------------------------------------------------
def create_reminder(client_phone=None, session_id=None, appointment_id=None,
                     due_date=None, note="", created_by="system") -> dict:
    rid = uuid.uuid4().hex[:10]
    now = _now()
    row = {
        "id": rid, "client_phone": client_phone, "session_id": session_id,
        "appointment_id": appointment_id, "due_date": due_date or date.today().isoformat(),
        "note": note, "status": "pending", "created_by": created_by,
        "created_at": now, "updated_at": now,
    }
    with _LOCK:
        c = _conn()
        c.execute(
            """
            INSERT INTO reminders (id, client_phone, session_id, appointment_id, due_date, note, status, created_by, created_at, updated_at)
            VALUES (:id,:client_phone,:session_id,:appointment_id,:due_date,:note,:status,:created_by,:created_at,:updated_at)
            """,
            row,
        )
        c.commit()
        c.close()
    return row


def list_reminders(phone: str | None = None, status: str | None = None, due_before: str | None = None, limit: int = 100) -> list[dict]:
    query = "SELECT * FROM reminders WHERE 1=1"
    params = []
    if phone:
        query += " AND client_phone=?"
        params.append(phone)
    if status:
        query += " AND status=?"
        params.append(status)
    if due_before:
        query += " AND due_date<=?"
        params.append(due_before)
    query += " ORDER BY due_date ASC LIMIT ?"
    params.append(limit)
    c = _conn()
    rows = c.execute(query, params).fetchall()
    c.close()
    return [dict(r) for r in rows]


def list_due_reminders(as_of: str | None = None) -> list[dict]:
    return list_reminders(status="pending", due_before=as_of or date.today().isoformat())


def get_reminder(reminder_id: str) -> dict | None:
    c = _conn()
    row = c.execute("SELECT * FROM reminders WHERE id=?", (reminder_id,)).fetchone()
    c.close()
    return dict(row) if row else None


def _set_reminder_status(reminder_id: str, status: str) -> dict | None:
    with _LOCK:
        c = _conn()
        c.execute("UPDATE reminders SET status=?, updated_at=? WHERE id=?", (status, _now(), reminder_id))
        c.commit()
        row = c.execute("SELECT * FROM reminders WHERE id=?", (reminder_id,)).fetchone()
        c.close()
    return dict(row) if row else None


def complete_reminder(reminder_id: str) -> dict | None:
    return _set_reminder_status(reminder_id, "done")


def cancel_reminder(reminder_id: str) -> dict | None:
    return _set_reminder_status(reminder_id, "cancelled")


# ---------------------------------------------------------------------------
# Aggregate view
# ---------------------------------------------------------------------------
def get_client_profile(phone: str, transcript_limit: int = 10) -> dict:
    import appointment_store as _appt_store  # local import avoids a hard cycle at module load

    client = get_client(phone) or {"phone": phone, "name": None, "email": None, "preferences": {}}
    return {
        "client": client,
        "appointment_history": _appt_store.list_all_by_phone(phone) if hasattr(_appt_store, "list_all_by_phone") else [],
        "reminders": list_reminders(phone=phone),
        "recent_transcripts": get_transcripts(phone=phone, limit=transcript_limit),
    }


init_db()
