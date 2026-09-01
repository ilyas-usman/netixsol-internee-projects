"""Week 7 Day 6 configuration — Testing, Evaluation & Security.

Purely additive: imports day5_config and day4_config settings and exposes Day 6
specific thresholds for prompt injection defense, performance evaluation targets,
and monitoring database options.
"""
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

from day5_config import (
    APPOINTMENT_DB,
    COMPANY_NAME,
    DAY5_TRACE_DB,
    load_employees,
)

# ---------------------------------------------------------------------------
# Day 6 Monitoring & Evaluation Databases
# ---------------------------------------------------------------------------
DAY6_MONITORING_DB = os.getenv("DAY6_MONITORING_DB", "./day6_monitoring.db")
DAY6_EVALUATION_REPORT_FILE = os.getenv("DAY6_EVALUATION_REPORT_FILE", "./day6_eval_report.json")

# Performance targets & thresholds for Task 3 & 4
TARGET_MAX_LATENCY_MS = float(os.getenv("TARGET_MAX_LATENCY_MS", "2500.0"))
TARGET_MIN_CONVERSATION_SUCCESS_RATE = float(os.getenv("TARGET_MIN_CONVERSATION_SUCCESS_RATE", "0.90"))
TARGET_MIN_BOOKING_SUCCESS_RATE = float(os.getenv("TARGET_MIN_BOOKING_SUCCESS_RATE", "0.95"))
TARGET_MAX_HALLUCINATION_RATE = float(os.getenv("TARGET_MAX_HALLUCINATION_RATE", "0.02"))

# Prompt Injection Defense Toggle
ENABLE_PROMPT_INJECTION_DEFENSE = os.getenv("ENABLE_PROMPT_INJECTION_DEFENSE", "true").strip().lower() in ("1", "true", "yes", "on")
