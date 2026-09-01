"""Week 7 Day 4 configuration — Calendar, Email, Scheduling.

This file only ADDS new settings on top of day3_config.py. Nothing here is
imported by Day 2/Day 3 code, and nothing in Day 2/Day 3 needs to change
for these defaults to be safe: every provider below has a working fallback
(local SQLite calendar, console/log email) so the app runs end-to-end even
before any Google/Gmail credentials are configured.
"""

import json
import os

from dotenv import load_dotenv

load_dotenv()


def _bool(name, default="false"):
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Google Calendar
# ---------------------------------------------------------------------------
# Recommended: a Google Cloud service account with domain-wide access to a
# single shared "Bookings" calendar. See day4-README.md for the full setup.
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_FILE",
    "./google_service_account.json",
)

GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")

GOOGLE_CALENDAR_TIMEZONE = os.getenv("GOOGLE_CALENDAR_TIMEZONE", "Asia/Karachi")

# Explicit on/off switch. If left as "auto" (default), Calendar is used when
# the service-account file exists and the Google client libraries are
# importable; otherwise the app transparently falls back to a local
# SQLite-backed calendar so booking/reschedule/cancel still work end-to-end.
CALENDAR_MODE = os.getenv("CALENDAR_MODE", "auto").strip().lower()


# ---------------------------------------------------------------------------
# Email — Gmail API and/or SMTP
# ---------------------------------------------------------------------------
# EMAIL_PROVIDER: "gmail_api" | "smtp" | "console" | "auto" (default)
# "auto" picks gmail_api if its credentials are present, else smtp if SMTP_*
# is set, else falls back to "console" (logs the email instead of sending —
# nothing ever crashes for lack of email credentials).
EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "auto").strip().lower()

# --- Gmail API (OAuth / domain-wide-delegated service account) ---
GMAIL_SERVICE_ACCOUNT_FILE = os.getenv(
    "GMAIL_SERVICE_ACCOUNT_FILE",
    "./google_service_account.json",
)
# The mailbox the Gmail API sends "as". Required for domain-wide delegation.
GMAIL_DELEGATED_USER = os.getenv("GMAIL_DELEGATED_USER", "")
# OAuth user-token flow (alternative to the service account for personal
# @gmail.com accounts that cannot use domain-wide delegation).
GMAIL_OAUTH_CLIENT_SECRET_FILE = os.getenv(
    "GMAIL_OAUTH_CLIENT_SECRET_FILE",
    "./gmail_oauth_client_secret.json",
)
GMAIL_OAUTH_TOKEN_FILE = os.getenv("GMAIL_OAUTH_TOKEN_FILE", "./gmail_oauth_token.json")

# --- SMTP (works with Gmail "App Passwords" or any SMTP provider) ---
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_USE_TLS = _bool("SMTP_USE_TLS", "true")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USER)
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "RealEstate Hub Scheduling")

# CC every employee-assignment email to a manager/admin inbox (optional).
ADMIN_NOTIFICATION_EMAIL = os.getenv("ADMIN_NOTIFICATION_EMAIL", "")

# Where console-mode "sends" get logged, so nothing is silently lost during
# development/demo before real email credentials are configured.
EMAIL_LOG_FILE = os.getenv("DAY4_EMAIL_LOG_FILE", "./appointment_emails.log")


# ---------------------------------------------------------------------------
# Business hours / scheduling rules
# ---------------------------------------------------------------------------
COMPANY_NAME = os.getenv("COMPANY_NAME", "RealEstate Hub")

BUSINESS_HOURS_START = os.getenv("BUSINESS_HOURS_START", "10:00")
BUSINESS_HOURS_END = os.getenv("BUSINESS_HOURS_END", "19:00")

# Python weekday numbers, Monday=0 .. Sunday=6. Default: closed on Sunday.
BUSINESS_DAYS = [
    int(x) for x in os.getenv("BUSINESS_DAYS", "0,1,2,3,4,5").split(",") if x.strip() != ""
]

APPOINTMENT_DURATION_MINUTES = int(os.getenv("APPOINTMENT_DURATION_MINUTES", "30"))

# How many days ahead a client may book.
MAX_BOOKING_HORIZON_DAYS = int(os.getenv("MAX_BOOKING_HORIZON_DAYS", "60"))


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
APPOINTMENT_DB = os.getenv("DAY4_APPOINTMENT_DB", "./appointments.db")

EMPLOYEES_FILE = os.getenv("DAY4_EMPLOYEES_FILE", "./employees.json")


def load_employees():
    """Return the configured employee directory (name, email, phone).

    Falls back to a single placeholder employee if employees.json is
    missing or unreadable, so appointment booking never hard-crashes for
    lack of a staff directory — it just visibly assigns "Front Desk".
    """
    try:
        with open(EMPLOYEES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list) and data:
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return [
        {"name": "Front Desk", "email": ADMIN_NOTIFICATION_EMAIL or "", "phone": "", "rating": 4.0}
    ]