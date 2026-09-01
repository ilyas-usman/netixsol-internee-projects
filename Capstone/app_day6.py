"""FastAPI entrypoint for Week 7 Day 6 — Testing, Evaluation & Security.

Extends app_day5.app without modifying a single line of previous Day endpoints:
- GET  /health & /api/health
- POST /api/day6/chat (with Prompt Injection Security Guardrails)
- GET  /api/day6/metrics
- POST /api/day6/evaluate
"""
from __future__ import annotations

import time
from fastapi import HTTPException
from pydantic import BaseModel

from app_day5 import app  # Purely additive mount on top of Day 5
from day5_agent import run_day5_turn
from day6_evaluator import evaluate_test_cases
from day6_monitoring import get_monitoring_summary, record_monitoring_metric
from day6_security import check_prompt_injection


class Day6TextTurn(BaseModel):
    session_id: str
    message: str
    known_phone: str | None = None


@app.get("/health")
@app.get("/api/health")
def health_check():
    """Task 5: Production Health Check Endpoint."""
    return {
        "status": "healthy",
        "service": "RealEstate Hub AI Agent",
        "version": "1.0.0",
        "day": 6,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@app.post("/api/day6/chat")
def day6_chat(req: Day6TextTurn):
    """Day 6 production chat endpoint with prompt injection defense & real-time monitoring."""
    t_start = time.perf_counter()

    # Task 2: Security check against prompt injection
    sec_res = check_prompt_injection(req.message)
    if sec_res["is_injection"]:
        latency_ms = (time.perf_counter() - t_start) * 1000
        record_monitoring_metric(
            session_id=req.session_id,
            latency_ms=latency_ms,
            api_failure=False,
            notes=f"Blocked prompt injection ({sec_res['attack_type']})",
        )
        return {
            "session_id": req.session_id,
            "response": sec_res["safe_response"],
            "intent": "security_block",
            "security_blocked": True,
            "attack_type": sec_res["attack_type"],
            "timings": {"total_ms": latency_ms},
        }

    # Standard Day 5 LangGraph agent execution
    result = run_day5_turn(req.session_id, req.message, known_phone=req.known_phone)
    latency_ms = (time.perf_counter() - t_start) * 1000
    result.setdefault("timings", {})["api_total_ms"] = latency_ms

    # Log turn to production monitoring metrics
    record_monitoring_metric(
        session_id=req.session_id,
        latency_ms=latency_ms,
        api_failure=False,
        booking_success=(result.get("intent") == "booking"),
    )

    return result


@app.get("/api/day6/metrics")
def day6_metrics():
    """Task 4: Real-time production metrics summary."""
    return get_monitoring_summary()


@app.post("/api/day6/evaluate")
def day6_run_evaluation(limit: int = 30):
    """Task 3 & 6: Execute automated evaluation suite on demand."""
    return evaluate_test_cases(limit=limit)
