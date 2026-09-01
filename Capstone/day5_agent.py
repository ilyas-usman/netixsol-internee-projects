"""Week 7 Day 5 — Orchestrator entry point.

High-level entry point `run_day5_turn(session_id, user_text, known_phone=None)`:
- Hydrates state from conversation_memory & CRM
- Runs the Day 5 LangGraph agent graph
- Records annotated execution traces
- Logs transcripts & updates memory
- Preserves 100% non-interference with existing Day 2/3/4 code
"""
from __future__ import annotations

import logging
import time
from typing import Any

from conversation_memory import add_turn, get_state, update_state
import crm_store
from day5_graph import DAY5_GRAPH, node_intent_detection, node_recommendation
from day5_state import (
    Day5AgentState,
    create_initial_day5_state,
    get_session_trace,
    record_transition,
)

_log = logging.getLogger("day5_agent")


def run_day5_turn(
    session_id: str,
    user_text: str,
    known_phone: str | None = None,
) -> dict[str, Any]:
    """Execute a single Day 5 turn using the Day 5 LangGraph StateGraph agent."""
    started = time.perf_counter()
    memory = get_state(session_id)

    # Resolve phone from known_phone parameter or CRM session link
    phone = known_phone or crm_store.get_phone_for_session(session_id)
    user_profile = crm_store.get_client(phone) if phone else {}

    # Initialize Day 5 State (Task 1)
    state = create_initial_day5_state(
        session_id=session_id,
        user_text=user_text,
        memory=memory,
        user_profile=user_profile,
    )

    # Execute LangGraph Graph (Task 2 & 4)
    if DAY5_GRAPH:
        final_state = DAY5_GRAPH.invoke(state)
    else:
        # Fallback node pipeline if langgraph is not installed
        final_state = node_intent_detection(state)
        final_state = node_recommendation(final_state)

    total_ms = (time.perf_counter() - started) * 1000
    final_state.setdefault("timings", {})["day5_total_ms"] = total_ms

    # Extract final output values
    response = final_state.get("response") or "Ji bilkul, main RealEstate Hub se aapki madad ke liye tayar hoon."
    slots = final_state.get("memory", {}).get("slots", {})

    # Update conversation memory
    update_state(
        session_id,
        slots=slots,
        last_shown_properties=final_state.get(
            "last_shown",
            memory.get("last_shown_properties", []),
        ),
        objections=final_state.get("memory", {}).get(
            "objections",
            memory.get("objections", {}),
        ),
    )

    add_turn(session_id, "user", user_text, {"slots": slots, "intent": final_state.get("intent")})
    add_turn(session_id, "assistant", response, {"timings": final_state.get("timings")})

    # Log turn to CRM transcript log
    try:
        crm_store.log_transcript(
            session_id=session_id,
            role="user",
            text=user_text,
            meta={"intent": final_state.get("intent")},
        )
        crm_store.log_transcript(
            session_id=session_id,
            role="assistant",
            text=response,
            meta={"timings": final_state.get("timings")},
        )
    except Exception:
        pass

    return {
        "session_id": session_id,
        "response": response,
        "intent": final_state.get("intent"),
        "route": {"route": final_state.get("intent")},
        "listings": final_state.get("listings", []),
        "tool_outputs": final_state.get("tool_outputs", []),
        "node_transitions": final_state.get("node_transitions", []),
        "appointment_status": final_state.get("appointment_status", {}),
        "memory": final_state.get("memory", memory),
        "timings": final_state.get("timings", {}),
    }


def get_trace_history(session_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """Task 5: Retrieve annotated execution traces for session."""
    return get_session_trace(session_id, limit=limit)
