"""Week 7 Day 6 — Task 4: Real-time Monitoring & Production Metrics Tracking.

Tracks system metrics into SQLite (`day6_monitoring.db`):
- Latency (latency_ms)
- Voice quality score (0.0 - 5.0)
- API failures
- Calendar failures
- Email failures
- Booking success rate
- RAG misses
"""
from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

from day6_config import DAY6_MONITORING_DB

_MONITOR_LOCK = threading.Lock()


def _get_conn():
    db_dir = os.path.dirname(os.path.abspath(DAY6_MONITORING_DB))
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DAY6_MONITORING_DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_monitoring_db():
    with _MONITOR_LOCK:
        c = _get_conn()
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS monitoring_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                latency_ms REAL NOT NULL DEFAULT 0.0,
                voice_quality INTEGER DEFAULT 5,
                api_failure INTEGER DEFAULT 0,
                calendar_failure INTEGER DEFAULT 0,
                email_failure INTEGER DEFAULT 0,
                booking_success INTEGER DEFAULT 0,
                rag_miss INTEGER DEFAULT 0,
                notes TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_mon_session ON monitoring_metrics(session_id);
            """
        )
        c.commit()
        c.close()


init_monitoring_db()


def record_monitoring_metric(
    session_id: str,
    latency_ms: float = 0.0,
    voice_quality: int = 5,
    api_failure: bool = False,
    calendar_failure: bool = False,
    email_failure: bool = False,
    booking_success: bool = False,
    rag_miss: bool = False,
    notes: str = "",
):
    """Task 4: Log turn metrics for production monitoring."""
    with _MONITOR_LOCK:
        try:
            c = _get_conn()
            c.execute(
                """
                INSERT INTO monitoring_metrics
                (session_id, timestamp, latency_ms, voice_quality, api_failure, calendar_failure, email_failure, booking_success, rag_miss, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    datetime.now(timezone.utc).isoformat(),
                    float(latency_ms),
                    int(voice_quality),
                    1 if api_failure else 0,
                    1 if calendar_failure else 0,
                    1 if email_failure else 0,
                    1 if booking_success else 0,
                    1 if rag_miss else 0,
                    notes,
                ),
            )
            c.commit()
            c.close()
        except Exception:
            pass


def get_monitoring_summary() -> dict[str, Any]:
    """Task 4: Return aggregated monitoring metrics summary."""
    c = _get_conn()
    row = c.execute(
        """
        SELECT
            COUNT(*) as total_turns,
            AVG(latency_ms) as avg_latency_ms,
            AVG(voice_quality) as avg_voice_quality,
            SUM(api_failure) as total_api_failures,
            SUM(calendar_failure) as total_calendar_failures,
            SUM(email_failure) as total_email_failures,
            SUM(booking_success) as total_booking_successes,
            SUM(rag_miss) as total_rag_misses
        FROM monitoring_metrics
        """
    ).fetchone()
    c.close()

    if not row or row["total_turns"] == 0:
        return {
            "total_turns": 0,
            "avg_latency_ms": 0.0,
            "avg_voice_quality": 5.0,
            "api_failures": 0,
            "calendar_failures": 0,
            "email_failures": 0,
            "booking_successes": 0,
            "rag_misses": 0,
        }

    return {
        "total_turns": row["total_turns"],
        "avg_latency_ms": round(float(row["avg_latency_ms"] or 0.0), 2),
        "avg_voice_quality": round(float(row["avg_voice_quality"] or 5.0), 2),
        "api_failures": int(row["total_api_failures"] or 0),
        "calendar_failures": int(row["total_calendar_failures"] or 0),
        "email_failures": int(row["total_email_failures"] or 0),
        "booking_successes": int(row["total_booking_successes"] or 0),
        "rag_misses": int(row["total_rag_misses"] or 0),
    }
