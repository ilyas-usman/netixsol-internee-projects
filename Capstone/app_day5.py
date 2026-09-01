"""FastAPI entrypoint for Week 7 Day 5 — LangGraph Orchestration & Tool Calling.

Extends app_day3.app without modifying a single line of Day 3/Day 4 endpoints:
- POST /api/day5/chat
- GET  /api/day5/trace/{session_id}
- GET  /api/day5/graph
"""
from __future__ import annotations

import time
from fastapi import HTTPException
from pydantic import BaseModel

from app_day3 import app  # Mounts on top of Day 3 / Day 4 app
from day5_agent import get_trace_history, run_day5_turn


class Day5TextTurn(BaseModel):
    session_id: str
    message: str
    known_phone: str | None = None


@app.post("/api/day5/chat")
def day5_chat(req: Day5TextTurn):
    """Day 5 turn endpoint backed by LangGraph state graph and tool calling."""
    started = time.perf_counter()
    result = run_day5_turn(req.session_id, req.message, known_phone=req.known_phone)
    result["timings"]["api_total_ms"] = (time.perf_counter() - started) * 1000
    return result


@app.get("/api/day5/trace/{session_id}")
def day5_session_trace(session_id: str, limit: int = 100):
    """Task 5: Retrieve annotated execution trace history for a session."""
    traces = get_trace_history(session_id, limit=limit)
    return {"session_id": session_id, "count": len(traces), "traces": traces}


@app.get("/api/day5/graph")
def day5_graph_structure():
    """Expose the Day 5 state graph node layout & routing architecture."""
    return {
        "nodes": [
            "intent_detection",
            "greeting",
            "goodbye",
            "rag",
            "recommendation",
            "booking",
            "rescheduling",
            "cancellation",
            "email",
            "clarification",
        ],
        "start_node": "intent_detection",
        "validation_rules": [
            "Never book unavailable slots",
            "Never recommend unavailable properties",
            "Ask clarification instead of guessing",
        ],
    }
