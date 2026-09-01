"""Week 7 Day 5 configuration — LangGraph Orchestration, Tool Calling & Tracing.

Purely additive: imports day4_config and day3_config and exposes Day 5 specific settings
for graph orchestration, execution tracing, tool timeouts, and validation rules.
"""
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

# Inherit settings from day4_config
from day4_config import (
    APPOINTMENT_DB,
    APPOINTMENT_DURATION_MINUTES,
    BUSINESS_DAYS,
    BUSINESS_HOURS_END,
    BUSINESS_HOURS_START,
    COMPANY_NAME,
    MAX_BOOKING_HORIZON_DAYS,
    load_employees,
)

# ---------------------------------------------------------------------------
# Day 5 Execution Tracing & State Logging
# ---------------------------------------------------------------------------
# Location for persistent execution trace logs for Day 5 graph runs
DAY5_TRACE_DB = os.getenv("DAY5_TRACE_DB", "./day5_traces.db")
DAY5_ENABLE_TRACE_LOGGING = os.getenv("DAY5_ENABLE_TRACE_LOGGING", "true").strip().lower() in ("1", "true", "yes", "on")

# Maximum trace records kept in memory per session
MAX_SESSION_TRACE_HISTORY = int(os.getenv("MAX_SESSION_TRACE_HISTORY", "100"))

# Validation Mode switches
ENABLE_STRICT_AVAILABILITY_CHECK = os.getenv("ENABLE_STRICT_AVAILABILITY_CHECK", "true").strip().lower() in ("1", "true", "yes", "on")
ENABLE_STRICT_PROPERTY_VERIFICATION = os.getenv("ENABLE_STRICT_PROPERTY_VERIFICATION", "true").strip().lower() in ("1", "true", "yes", "on")
ENABLE_CLARIFICATION_MODE = os.getenv("ENABLE_CLARIFICATION_MODE", "true").strip().lower() in ("1", "true", "yes", "on")
