"""Week 7 Day 4 — Task 5: CRM conversational commands.

`handle_crm_turn(session_id, user_text, memory)` follows the exact same
contract as appointment_agent.handle_appointment_turn(): return None when
the turn isn't CRM-related, otherwise return a run_turn()-shaped result.
Wired into day3_agent.run_turn() the same additive way, checked BEFORE the
appointment agent so it never fights an in-progress booking/reschedule/
cancel flow (see has_active_draft()).

Call transcripts and client preferences are logged unconditionally for
every turn by log_turn_to_crm() (also called from run_turn) — that part
needs no user-visible intent at all, it just happens in the background.
"""
from __future__ import annotations

import re
import time
from datetime import date, timedelta

import crm_store
from appointment_agent import _extract_date, _extract_notes, _extract_phone, _norm, has_active_draft
from crm_config import MANUAL_REMINDER_DEFAULT_DAYS, PROFILE_TRANSCRIPT_LIMIT

REMINDER_LIST_MARKERS = (
    "reminders dikhao", "meri reminders", "pending follow up", "pending follow-ups",
    "follow ups dikhao", "show reminders", "list reminders", "show my reminders",
    "فالو اپ دکھائیں", "ریمائنڈر دکھائیں",
)

REMINDER_ADD_MARKERS = (
    "reminder add", "add reminder", "reminder set", "set a reminder", "set reminder",
    "yaad dilana", "yaad dila dena", "follow up karna hai", "follow-up karna hai",
    "followup karna hai", "reminder banao", "ریمائنڈر لگا دیں", "یاد دلانا",
)

HISTORY_MARKERS = (
    "client history", "customer history", "meri history", "mera profile",
    "profile dikhao", "history dikhao", "purani appointments", "client profile",
    "show client history", "کلائنٹ کی تاریخ", "پروفائل دکھائیں",
)

DAYS_AHEAD_PATTERN = re.compile(r"\b(\d{1,2})\s*(?:din|days?)\s*(?:baad|later|mein)?\b")


def is_reminder_list_intent(text):
    s = _norm(text)
    return any(m in s for m in REMINDER_LIST_MARKERS)


def is_reminder_add_intent(text):
    s = _norm(text)
    return any(m in s for m in REMINDER_ADD_MARKERS)


def is_history_intent(text):
    s = _norm(text)
    return any(m in s for m in HISTORY_MARKERS)


def _extract_due_date(text):
    s = _norm(text)
    m = DAYS_AHEAD_PATTERN.search(s)
    if m:
        return (date.today() + timedelta(days=int(m.group(1)))).isoformat()
    return _extract_date(text)


def _resolve_phone(session_id, text):
    return _extract_phone(text) or crm_store.get_phone_for_session(session_id)


def _result(response, memory, timings):
    return {
        "response": response,
        "listings": [],
        "route": "crm",
        "memory": memory,
        "objection_category": None,
        "escalation": False,
        "timings": timings,
    }


def _handle_history(session_id, text, memory):
    phone = _resolve_phone(session_id, text)
    if not phone:
        return "Kis client ka profile/history dekhna hai? Unka phone number bata dein."

    profile = crm_store.get_client_profile(phone, transcript_limit=PROFILE_TRANSCRIPT_LIMIT)
    client = profile["client"]
    prefs = client.get("preferences", {})
    appts = profile["appointment_history"]
    pending_reminders = [r for r in profile["reminders"] if r["status"] == "pending"]

    lines = [f"Client: {client.get('name') or 'N/A'} ({phone})"]
    if prefs:
        pref_bits = ", ".join(f"{k}: {v}" for k, v in prefs.items())
        lines.append(f"Preferences: {pref_bits}")
    else:
        lines.append("Abhi tak koi preferences record nahi hui.")

    if appts:
        latest = appts[0]
        lines.append(
            f"Total appointments: {len(appts)} (latest: {latest['appt_date']} {latest['appt_time']} — {latest['status']})"
        )
    else:
        lines.append("Koi appointment history nahi mili.")

    if pending_reminders:
        nxt = pending_reminders[0]
        lines.append(f"Pending follow-ups: {len(pending_reminders)} (agla: {nxt['due_date']} — {nxt['note']})")
    else:
        lines.append("Koi pending follow-up nahi hai.")

    return "\n".join(lines)


def _handle_reminder_add(session_id, text, memory):
    phone = _resolve_phone(session_id, text)
    if not phone:
        return "Kis client ke liye follow-up reminder set karna hai? Unka phone number bata dein."

    explicit_due = _extract_due_date(text)
    due = explicit_due or (date.today() + timedelta(days=MANUAL_REMINDER_DEFAULT_DAYS)).isoformat()
    note = _extract_notes(text) or text.strip()

    crm_store.upsert_client(phone)
    crm_store.link_session(session_id, phone)
    reminder = crm_store.create_reminder(
        client_phone=phone, session_id=session_id, due_date=due, note=note, created_by="staff"
    )
    default_note = (
        f" (koi tareekh nahi di gayi thi, isliye default {MANUAL_REMINDER_DEFAULT_DAYS} din baad set kiya — badalna ho to bata dein)"
        if not explicit_due
        else ""
    )
    return f"Ji, follow-up reminder set kar diya gaya hai — {due} ko{default_note}. (ID: {reminder['id']})"


def _handle_reminder_list(session_id, text, memory):
    phone = _resolve_phone(session_id, text)
    if not phone:
        return "Kis client ki reminders dekhni hain? Phone number bata dein."
    pending = [r for r in crm_store.list_reminders(phone=phone) if r["status"] == "pending"]
    if not pending:
        return "Is client ke liye koi pending follow-up reminder nahi hai."
    lines = [f"{r['due_date']}: {r['note']} (ID: {r['id']})" for r in pending]
    return "Pending follow-ups:\n" + "\n".join(lines)


def handle_crm_turn(session_id, user_text, memory):
    """Return a run_turn()-shaped result dict, or None to defer."""
    if has_active_draft(session_id):
        # Never interrupt an in-progress booking/reschedule/cancel flow.
        return None

    started = time.perf_counter()
    if is_reminder_list_intent(user_text):
        response = _handle_reminder_list(session_id, user_text, memory)
    elif is_reminder_add_intent(user_text):
        response = _handle_reminder_add(session_id, user_text, memory)
    elif is_history_intent(user_text):
        response = _handle_history(session_id, user_text, memory)
    else:
        return None

    timings = {"crm_ms": (time.perf_counter() - started) * 1000}
    timings["total_ms"] = timings["crm_ms"]
    return _result(response, memory, timings)


# ---------------------------------------------------------------------------
# Unconditional per-turn logging (Task 5 — call transcripts + preferences).
# Called from day3_agent.run_turn() for every turn, regardless of route.
# ---------------------------------------------------------------------------
def log_turn_to_crm(session_id, user_text, result, memory, channel="chat"):
    phone = _extract_phone(user_text) or crm_store.get_phone_for_session(session_id)
    if phone:
        crm_store.link_session(session_id, phone)
        slots = (result.get("memory") or memory or {}).get("slots") or {}
        crm_store.merge_preferences(phone, slots)

    crm_store.log_transcript(session_id, "user", user_text, channel=channel)
    response_text = (result or {}).get("response", "")
    crm_store.log_transcript(session_id, "assistant", response_text, channel=channel)
