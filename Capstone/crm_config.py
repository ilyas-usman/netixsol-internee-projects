"""Week 7 Day 4 — Task 5: CRM configuration.

Kept as its own file (rather than folding into day4_config.py) since the
CRM is a distinct concern from Calendar/Email, even though it lives
alongside the same Day 4 work. Nothing here is required by Day 2/3/4
Tasks 1-3 — this only adds a logging/history layer on top of them.
"""
import os

from dotenv import load_dotenv

load_dotenv()

CRM_DB = os.getenv("CRM_DB", "./crm.db")

# Slots from conversation_memory.heuristic_slots() worth persisting as a
# client's standing preferences once we know who they are (phone-linked).
PREFERENCE_SLOT_KEYS = ("budget", "city", "location", "bedrooms", "purpose", "property_type")

# How far out to auto-schedule a follow-up after a completed visit.
POST_VISIT_FOLLOWUP_DELAY_DAYS = int(os.getenv("CRM_POST_VISIT_FOLLOWUP_DAYS", "1"))

# "Win-back" follow-up offered after a cancellation.
CANCELLATION_WINBACK_DELAY_DAYS = int(os.getenv("CRM_CANCELLATION_WINBACK_DAYS", "3"))

# Default due date for a manually-requested reminder that didn't include one.
MANUAL_REMINDER_DEFAULT_DAYS = int(os.getenv("CRM_MANUAL_REMINDER_DEFAULT_DAYS", "3"))

# How many recent transcript turns to show in a client profile view.
PROFILE_TRANSCRIPT_LIMIT = int(os.getenv("CRM_PROFILE_TRANSCRIPT_LIMIT", "10"))
