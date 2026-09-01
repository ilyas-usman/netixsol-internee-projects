"""Week 7 Day 5 — Task 1: LangGraph State Design & State Tracing.

Defines `Day5AgentState` (TypedDict) as required by Task 1:
1. conversation_history
2. user_profile
3. property_preferences
4. budget
5. intent
6. tool_outputs
7. appointment_status
8. node_transitions (Annotated execution trace)
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, TypedDict

from day5_config import DAY5_TRACE_DB

_TRACE_LOCK = threading.Lock()


def _get_trace_conn():
    db_dir = os.path.dirname(os.path.abspath(DAY5_TRACE_DB))
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DAY5_TRACE_DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_trace_db():
    with _TRACE_LOCK:
        c = _get_trace_conn()
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS session_traces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                from_node TEXT NOT NULL,
                to_node TEXT NOT NULL,
                intent TEXT,
                reason TEXT,
                state_summary_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_trace_session ON session_traces(session_id);
            """
        )
        c.commit()
        c.close()


init_trace_db()


class Day5AgentState(TypedDict, total=False):
    # Core Task 1 State Design Requirements
    session_id: str
    user_text: str
    conversation_history: list[dict[str, Any]]
    user_profile: dict[str, Any]
    property_preferences: dict[str, Any]
    budget: float | int | None
    intent: str
    tool_outputs: list[dict[str, Any]]
    appointment_status: dict[str, Any]
    node_transitions: list[dict[str, Any]]

    # Operational execution & routing attributes
    memory: dict[str, Any]
    route: dict[str, Any]
    response: str
    timings: dict[str, float]
    listings: list[dict[str, Any]]
    last_shown: list[dict[str, Any]]
    sql_context: str
    rag_hits: list[dict[str, Any]]
    objection_category: str
    escalation: bool
    clarification_needed: dict[str, Any] | None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_initial_day5_state(
    session_id: str,
    user_text: str,
    memory: dict[str, Any] | None = None,
    user_profile: dict[str, Any] | None = None,
) -> Day5AgentState:
    memory = memory or {"slots": {}, "history": [], "objections": {}}
    slots = memory.get("slots") or {}

    history = []
    for turn in memory.get("history", []):
        history.append({
            "role": turn.get("role"),
            "text": turn.get("text"),
            "timestamp": turn.get("timestamp", now_iso()),
        })

    budget = slots.get("budget")
    preferences = {
        "city": slots.get("city"),
        "location": slots.get("location"),
        "property_type": slots.get("property_type"),
        "unit_type": slots.get("unit_type"),
        "bedrooms": slots.get("bedrooms"),
        "purpose": slots.get("purpose"),
        "exclude_location": slots.get("exclude_location"),
    }

    return Day5AgentState(
        session_id=session_id,
        user_text=user_text,
        conversation_history=history,
        user_profile=user_profile or {},
        property_preferences=preferences,
        budget=budget,
        intent="unknown",
        tool_outputs=[],
        appointment_status={},
        node_transitions=[],
        memory=memory,
        route={},
        response="",
        timings={},
        listings=[],
        last_shown=memory.get("last_shown_properties", []),
        sql_context="",
        rag_hits=[],
        objection_category="none",
        escalation=False,
        clarification_needed=None,
    )


def record_transition(
    state: Day5AgentState,
    from_node: str,
    to_node: str,
    reason: str = "",
) -> Day5AgentState:
    """Task 5: Log every node transition and append an annotated execution trace record."""
    transitions = list(state.get("node_transitions") or [])
    ts = now_iso()

    record = {
        "timestamp": ts,
        "from_node": from_node,
        "to_node": to_node,
        "intent": state.get("intent", "unknown"),
        "reason": reason,
        "state_summary": {
            "budget": state.get("budget"),
            "city": (state.get("property_preferences") or {}).get("city"),
            "location": (state.get("property_preferences") or {}).get("location"),
            "property_type": (state.get("property_preferences") or {}).get("property_type"),
            "tools_count": len(state.get("tool_outputs") or []),
            "has_appointment": bool(state.get("appointment_status")),
        },
    }

    transitions.append(record)
    state["node_transitions"] = transitions

    # Persist transition to trace DB
    with _TRACE_LOCK:
        try:
            c = _get_trace_conn()
            c.execute(
                """
                INSERT INTO session_traces (session_id, timestamp, from_node, to_node, intent, reason, state_summary_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state.get("session_id", "unknown"),
                    ts,
                    from_node,
                    to_node,
                    state.get("intent", "unknown"),
                    reason,
                    json.dumps(record["state_summary"], ensure_ascii=False),
                ),
            )
            c.commit()
            c.close()
        except Exception:
            pass

    return state


def get_session_trace(session_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """Retrieve full annotated execution traces for a session (Task 5)."""
    c = _get_trace_conn()
    rows = c.execute(
        """
        SELECT * FROM session_traces
        WHERE session_id = ?
        ORDER BY id ASC LIMIT ?
        """,
        (session_id, limit),
    ).fetchall()
    c.close()

    trace = []
    for r in rows:
        trace.append({
            "id": r["id"],
            "session_id": r["session_id"],
            "timestamp": r["timestamp"],
            "from_node": r["from_node"],
            "to_node": r["to_node"],
            "intent": r["intent"],
            "reason": r["reason"],
            "state_summary": json.loads(r["state_summary_json"] or "{}"),
        })
    return trace
