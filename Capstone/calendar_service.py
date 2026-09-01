"""Week 7 Day 4 — Google Calendar integration with an automatic local fallback.

Follows the same optional-dependency pattern already used elsewhere in this
project (see the `try: from groq import Groq / except ImportError` and
`try: from langgraph.graph import ...` guards in day3_agent.py): the Google
client libraries are imported lazily and only if available, so nothing here
can break the app for a machine that has not `pip install`-ed them yet, or
before real Google credentials exist.

Two providers implement the same small interface:
- GoogleCalendarProvider — real Google Calendar events (see day4-README.md
  for the service-account setup).
- LocalCalendarProvider  — appointments.db is treated as the calendar. Used
  automatically whenever Google credentials/libraries are not available, so
  booking/reschedule/cancel and double-booking checks all still work with
  zero external setup.
"""
from __future__ import annotations

import datetime as dt
import os

import appointment_store as store
from day4_config import (
    CALENDAR_MODE,
    GOOGLE_CALENDAR_ID,
    GOOGLE_CALENDAR_TIMEZONE,
    GOOGLE_SERVICE_ACCOUNT_FILE,
)

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build as google_build
except ImportError:  # google-api-python-client / google-auth not installed
    service_account = None
    google_build = None


class CalendarError(Exception):
    """Raised when a calendar operation fails in a way the caller should surface."""


class LocalCalendarProvider:
    """Fallback calendar backed by appointment_store.appointments.

    This is what keeps Task 3 (booking/reschedule/cancellation) fully
    functional before any Google Cloud setup happens.
    """

    name = "local"

    def is_slot_free(self, employee_name: str, appt_date: str, appt_time: str, duration_minutes: int, exclude_appt_id: str | None = None) -> bool:
        existing = store.list_for_employee_day(employee_name, appt_date)
        start = _to_minutes(appt_time)
        end = start + duration_minutes
        for row in existing:
            if exclude_appt_id and row["id"] == exclude_appt_id:
                continue
            other_start = _to_minutes(row["appt_time"])
            other_end = other_start + int(row.get("duration_minutes") or 30)
            if start < other_end and other_start < end:
                return False
        return True

    def create_event(self, *, employee_name, employee_email, client_name, client_phone,
                      property_label, appt_date, appt_time, duration_minutes, notes):
        # No external event id — the appointment row's own id is authoritative.
        return {"event_id": None, "provider": self.name}

    def update_event(self, event_id, **fields):
        return {"event_id": event_id, "provider": self.name}

    def delete_event(self, event_id):
        return True


class GoogleCalendarProvider:
    """Real Google Calendar via a service account."""

    name = "google"

    def __init__(self):
        scopes = ["https://www.googleapis.com/auth/calendar"]
        creds = service_account.Credentials.from_service_account_file(
            GOOGLE_SERVICE_ACCOUNT_FILE, scopes=scopes
        )
        self._service = google_build("calendar", "v3", credentials=creds, cache_discovery=False)
        self._calendar_id = GOOGLE_CALENDAR_ID
        self._tz = GOOGLE_CALENDAR_TIMEZONE

    def _bounds(self, appt_date, appt_time, duration_minutes):
        start = dt.datetime.strptime(f"{appt_date} {appt_time}", "%Y-%m-%d %H:%M")
        if ZoneInfo and self._tz:
            try:
                start = start.replace(tzinfo=ZoneInfo(self._tz))
            except Exception:
                pass
        end = start + dt.timedelta(minutes=duration_minutes)
        return start, end

    def is_slot_free(self, employee_name, appt_date, appt_time, duration_minutes, exclude_appt_id=None):
        start, end = self._bounds(appt_date, appt_time, duration_minutes)
        body = {
            "timeMin": start.isoformat(),
            "timeMax": end.isoformat(),
            "timeZone": self._tz,
            "items": [{"id": self._calendar_id}],
        }
        try:
            result = self._service.freebusy().query(body=body).execute()
            busy = result["calendars"][self._calendar_id]["busy"]
        except Exception as exc:  # network/auth failure — fail safe to "unknown", let caller decide
            raise CalendarError(f"Google Calendar freebusy check failed: {exc}") from exc
        return len(busy) == 0

    def create_event(self, *, employee_name, employee_email, client_name, client_phone,
                      property_label, appt_date, appt_time, duration_minutes, notes):
        start, end = self._bounds(appt_date, appt_time, duration_minutes)
        attendees = []
        if employee_email:
            attendees.append({"email": employee_email})
        body = {
            "summary": f"Property viewing — {client_name or 'Client'} x {employee_name or 'Agent'}",
            "description": (
                f"Client: {client_name or 'N/A'}\n"
                f"Phone: {client_phone or 'N/A'}\n"
                f"Employee: {employee_name or 'N/A'}\n"
                f"Property: {property_label or 'N/A'}\n"
                f"Notes: {notes or 'N/A'}"
            ),
            "start": {"dateTime": start.isoformat(), "timeZone": self._tz},
            "end": {"dateTime": end.isoformat(), "timeZone": self._tz},
            "attendees": attendees,
        }
        try:
            event = self._service.events().insert(
                calendarId=self._calendar_id, body=body, sendUpdates="none"
            ).execute()
        except Exception as exc:
            if "forbiddenForServiceAccounts" in str(exc) and body.get("attendees"):
                try:
                    body.pop("attendees", None)
                    event = self._service.events().insert(
                        calendarId=self._calendar_id, body=body, sendUpdates="none"
                    ).execute()
                except Exception as exc2:
                    raise CalendarError(f"Google Calendar event creation failed: {exc2}") from exc2
            else:
                raise CalendarError(f"Google Calendar event creation failed: {exc}") from exc
        return {"event_id": event.get("id"), "provider": self.name}

    def update_event(self, event_id, **fields):
        if not event_id:
            return self.create_event(**fields)
        appt_date = fields["appt_date"]
        appt_time = fields["appt_time"]
        duration_minutes = fields["duration_minutes"]
        start, end = self._bounds(appt_date, appt_time, duration_minutes)
        body = {
            "start": {"dateTime": start.isoformat(), "timeZone": self._tz},
            "end": {"dateTime": end.isoformat(), "timeZone": self._tz},
            "description": (
                f"Client: {fields.get('client_name') or 'N/A'}\n"
                f"Phone: {fields.get('client_phone') or 'N/A'}\n"
                f"Employee: {fields.get('employee_name') or 'N/A'}\n"
                f"Property: {fields.get('property_label') or 'N/A'}\n"
                f"Notes: {fields.get('notes') or 'N/A'}\n"
                f"(Rescheduled)"
            ),
        }
        try:
            event = self._service.events().patch(
                calendarId=self._calendar_id, eventId=event_id, body=body, sendUpdates="none"
            ).execute()
        except Exception as exc:
            raise CalendarError(f"Google Calendar event update failed: {exc}") from exc
        return {"event_id": event.get("id"), "provider": self.name}

    def delete_event(self, event_id):
        if not event_id:
            return True
        try:
            self._service.events().delete(
                calendarId=self._calendar_id, eventId=event_id, sendUpdates="none"
            ).execute()
        except Exception as exc:
            raise CalendarError(f"Google Calendar event deletion failed: {exc}") from exc
        return True


def _to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


_provider = None


def get_calendar_provider():
    """Return the active calendar provider, choosing Google when configured
    and available, otherwise the local fallback. Cached after first call."""
    global _provider
    if _provider is not None:
        return _provider

    if CALENDAR_MODE == "local":
        _provider = LocalCalendarProvider()
        return _provider

    can_use_google = (
        CALENDAR_MODE in ("auto", "google")
        and google_build is not None
        and service_account is not None
        and os.path.exists(GOOGLE_SERVICE_ACCOUNT_FILE)
    )
    if can_use_google:
        try:
            _provider = GoogleCalendarProvider()
            return _provider
        except Exception:
            if CALENDAR_MODE == "google":
                raise
            # fall through to local provider in "auto" mode
    _provider = LocalCalendarProvider()
    return _provider
