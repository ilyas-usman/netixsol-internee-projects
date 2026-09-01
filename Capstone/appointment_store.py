"""Week 7 Day 4 — persistent appointment storage.

Deliberately uses its OWN sqlite file (appointments.db, configurable via
DAY4_APPOINTMENT_DB) instead of touching day3_memory.db. This keeps
conversation_memory.py's schema and every Day 3 table 100% unchanged.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

from day4_config import APPOINTMENT_DB

_LOCK = threading.Lock()


def _conn():
    db_dir = os.path.dirname(os.path.abspath(APPOINTMENT_DB))
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    c = sqlite3.connect(APPOINTMENT_DB, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _LOCK:
        c = _conn()
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS appointments (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                channel TEXT NOT NULL DEFAULT 'chat',
                client_name TEXT,
                client_phone TEXT,
                client_email TEXT,
                employee_name TEXT,
                employee_email TEXT,
                property_id TEXT,
                property_label TEXT,
                appt_date TEXT NOT NULL,
                appt_time TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL DEFAULT 30,
                notes TEXT,
                status TEXT NOT NULL DEFAULT 'booked',
                calendar_event_id TEXT,
                calendar_provider TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_appt_session ON appointments(session_id);
            CREATE INDEX IF NOT EXISTS idx_appt_date ON appointments(appt_date, appt_time);
            CREATE INDEX IF NOT EXISTS idx_appt_employee ON appointments(employee_name, appt_date);
            CREATE INDEX IF NOT EXISTS idx_appt_phone ON appointments(client_phone);

            CREATE TABLE IF NOT EXISTS appointment_drafts (
                session_id TEXT PRIMARY KEY,
                draft_json TEXT NOT NULL DEFAULT '{}',
                stage TEXT NOT NULL DEFAULT 'collecting',
                intent TEXT NOT NULL DEFAULT 'book',
                target_appointment_id TEXT,
                updated_at TEXT NOT NULL
            );
            """
        )
        c.commit()
        c.close()


def _now():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Drafts (in-progress booking / reschedule / cancel conversation state)
# ---------------------------------------------------------------------------
def get_draft(session_id: str) -> dict:
    c = _conn()
    row = c.execute(
        "SELECT * FROM appointment_drafts WHERE session_id=?", (session_id,)
    ).fetchone()
    c.close()
    if not row:
        return {}
    return {
        "session_id": row["session_id"],
        "slots": json.loads(row["draft_json"] or "{}"),
        "stage": row["stage"],
        "intent": row["intent"],
        "target_appointment_id": row["target_appointment_id"],
    }


def save_draft(session_id: str, slots: dict, stage: str, intent: str, target_appointment_id: str | None = None):
    with _LOCK:
        c = _conn()
        c.execute(
            """
            INSERT INTO appointment_drafts(session_id, draft_json, stage, intent, target_appointment_id, updated_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(session_id) DO UPDATE SET
                draft_json=excluded.draft_json,
                stage=excluded.stage,
                intent=excluded.intent,
                target_appointment_id=excluded.target_appointment_id,
                updated_at=excluded.updated_at
            """,
            (session_id, json.dumps(slots, ensure_ascii=False), stage, intent, target_appointment_id, _now()),
        )
        c.commit()
        c.close()


def clear_draft(session_id: str):
    with _LOCK:
        c = _conn()
        c.execute("DELETE FROM appointment_drafts WHERE session_id=?", (session_id,))
        c.commit()
        c.close()


# ---------------------------------------------------------------------------
# Appointments
# ---------------------------------------------------------------------------
def create_appointment(**fields) -> dict:
    appt_id = fields.get("id") or uuid.uuid4().hex[:10]
    now = _now()
    row = {
        "id": appt_id,
        "session_id": fields.get("session_id", ""),
        "channel": fields.get("channel", "chat"),
        "client_name": fields.get("client_name"),
        "client_phone": fields.get("client_phone"),
        "client_email": fields.get("client_email"),
        "employee_name": fields.get("employee_name"),
        "employee_email": fields.get("employee_email"),
        "property_id": fields.get("property_id"),
        "property_label": fields.get("property_label"),
        "appt_date": fields["appt_date"],
        "appt_time": fields["appt_time"],
        "duration_minutes": fields.get("duration_minutes", 30),
        "notes": fields.get("notes", ""),
        "status": fields.get("status", "booked"),
        "calendar_event_id": fields.get("calendar_event_id"),
        "calendar_provider": fields.get("calendar_provider"),
        "created_at": now,
        "updated_at": now,
    }
    with _LOCK:
        c = _conn()
        c.execute(
            """
            INSERT INTO appointments (
                id, session_id, channel, client_name, client_phone, client_email,
                employee_name, employee_email, property_id, property_label,
                appt_date, appt_time, duration_minutes, notes, status,
                calendar_event_id, calendar_provider, created_at, updated_at
            ) VALUES (:id,:session_id,:channel,:client_name,:client_phone,:client_email,
                :employee_name,:employee_email,:property_id,:property_label,
                :appt_date,:appt_time,:duration_minutes,:notes,:status,
                :calendar_event_id,:calendar_provider,:created_at,:updated_at)
            """,
            row,
        )
        c.commit()
        c.close()
    return row


def update_appointment(appt_id: str, **fields) -> dict | None:
    with _LOCK:
        c = _conn()
        current = c.execute("SELECT * FROM appointments WHERE id=?", (appt_id,)).fetchone()
        if not current:
            c.close()
            return None
        merged = dict(current)
        merged.update(fields)
        merged["updated_at"] = _now()
        c.execute(
            """
            UPDATE appointments SET
                client_name=:client_name, client_phone=:client_phone, client_email=:client_email,
                employee_name=:employee_name, employee_email=:employee_email,
                property_id=:property_id, property_label=:property_label,
                appt_date=:appt_date, appt_time=:appt_time, duration_minutes=:duration_minutes,
                notes=:notes, status=:status, calendar_event_id=:calendar_event_id,
                calendar_provider=:calendar_provider, updated_at=:updated_at
            WHERE id=:id
            """,
            merged,
        )
        c.commit()
        c.close()
    return merged


def get_appointment(appt_id: str) -> dict | None:
    c = _conn()
    row = c.execute("SELECT * FROM appointments WHERE id=?", (appt_id,)).fetchone()
    c.close()
    return dict(row) if row else None


def find_upcoming_by_session(session_id: str) -> dict | None:
    c = _conn()
    row = c.execute(
        """
        SELECT * FROM appointments
        WHERE session_id=? AND status IN ('booked','rescheduled')
        ORDER BY appt_date DESC, appt_time DESC LIMIT 1
        """,
        (session_id,),
    ).fetchone()
    c.close()
    return dict(row) if row else None


def find_upcoming_by_phone(phone: str) -> list[dict]:
    if not phone:
        return []
    c = _conn()
    rows = c.execute(
        """
        SELECT * FROM appointments
        WHERE client_phone=? AND status IN ('booked','rescheduled')
        ORDER BY appt_date ASC, appt_time ASC
        """,
        (phone,),
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def list_all_by_phone(phone: str) -> list[dict]:
    """Full appointment history for a client (Task 5 CRM), every status
    included, most recent first. Distinct from find_upcoming_by_phone,
    which only returns active bookings."""
    if not phone:
        return []
    c = _conn()
    rows = c.execute(
        "SELECT * FROM appointments WHERE client_phone=? ORDER BY appt_date DESC, appt_time DESC",
        (phone,),
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def list_for_employee_day(employee_name: str, appt_date: str) -> list[dict]:
    c = _conn()
    rows = c.execute(
        """
        SELECT * FROM appointments
        WHERE employee_name=? AND appt_date=? AND status IN ('booked','rescheduled')
        ORDER BY appt_time ASC
        """,
        (employee_name, appt_date),
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def list_appointments(session_id: str | None = None, limit: int = 50) -> list[dict]:
    c = _conn()
    if session_id:
        rows = c.execute(
            "SELECT * FROM appointments WHERE session_id=? ORDER BY created_at DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT * FROM appointments ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def cancel_appointment(appt_id: str) -> dict | None:
    return update_appointment(appt_id, status="cancelled")


init_db()
