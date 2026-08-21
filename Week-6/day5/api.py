"""
Capstone Task 3 — FastAPI wrapper around the LangGraph AFL agent.

Endpoint: POST /chat
  Request:  {"message": str, "conversation_id": str}
  Response: {"response": str, "conversation_id": str, "grounded": bool,
             "unverified_numbers": [float], "tools_called": [str],
             "latency_ms": float, "error": str | None}

Structured logging (Task 3): every request writes one JSON line to
logs/requests.jsonl containing query, tools called, latency, and an
approximate token-usage estimate — the foundation for the monitoring
plan in monitoring.md. This is intentionally file-based JSONL rather than
a database, since the brief asks for "the foundation for monitoring," not
a production observability stack; the log format is what a real
log-shipper (Datadog, CloudWatch, etc.) would ingest with zero changes.

Rate/abuse handling (Task 1): a simple in-memory sliding-window limiter
per conversation_id AND per client IP, since a single conversation_id can
be spoofed/reused by a hostile client, but IP alone breaks legitimate
multi-user setups behind NAT/a shared proxy — checking both catches more
abuse patterns than either alone. This is intentionally simple (in-memory,
resets on restart) — a production deployment would move this to Redis or
an API gateway, noted in monitoring.md.

Run:
    pip install fastapi uvicorn
    uvicorn api:app --reload --port 8000

Try it:
    curl -X POST http://localhost:8000/chat \
      -H "Content-Type: application/json" \
      -d '{"message": "Who had the highest disposals in round 5, 2022?", "conversation_id": "demo-1"}'
"""

import json
import os
import re
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from agent import ToolCallLogger, ask, build_agent

# ---------------------------------------------------------------------------
# Startup: build the agent ONCE per process, not per request. The
# checkpointer's per-thread memory and the dataset dataframes are all
# loaded here; every request reuses this single instance.
# ---------------------------------------------------------------------------
app = FastAPI(title="AFL Domain-Scoped Chat Agent", version="1.0.0")
_agent = build_agent()
_logger = ToolCallLogger()

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "requests.jsonl"

# --- Rate limiting (Task 1: abuse handling) ---------------------------------
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_REQUESTS = 20  # per window, per key (conversation_id or IP)
_request_timestamps: dict[str, deque] = defaultdict(deque)


def _check_rate_limit(key: str) -> bool:
    """Sliding window: True if this key is still within the allowed rate,
    False if it should be rejected. Purges timestamps older than the
    window on every call, so memory doesn't grow unbounded for a
    long-lived key."""
    now = time.monotonic()
    dq = _request_timestamps[key]
    while dq and now - dq[0] > RATE_LIMIT_WINDOW_SECONDS:
        dq.popleft()
    if len(dq) >= RATE_LIMIT_MAX_REQUESTS:
        return False
    dq.append(now)
    return True


# --- Off-topic-probing / repeated-injection detection (Task 1) -------------
# Track how many times each conversation_id has been declined for scope
# reasons — a high count is a signal worth logging distinctly (a human
# genuinely curious about AFL rarely gets declined 5+ times in a row; a
# scripted probing/injection attempt often does). This does NOT block the
# conversation (declining is already the correct behavior each time) — it
# only flags the pattern in the structured log for monitoring to pick up,
# per Task 4's "off-topic leak rate" tracking.
_DECLINE_PHRASES = ("i can only help with afl", "i'm not able to", "i can't help with that")
_decline_counts: dict[str, int] = defaultdict(int)


def _looks_declined(answer: str) -> bool:
    lowered = answer.lower()
    return any(p in lowered for p in _DECLINE_PHRASES)


# --- Leakage safety net -------------------------------------------------
# Belt-and-suspenders on top of tools.py already never emitting raw IDs
# (audited — every tool return string goes through _player_display_name,
# never row['player_id'] or row['id']): strip any standalone token that
# looks like an internal numeric ID pattern our own logs might use
# (e.g. "player_id=101" or "_info_id: 101") before the response leaves
# the API boundary, in case a future tool addition forgets the
# convention. This is intentionally narrow (specific key=value / key:
# patterns only) so it never mangles a legitimate stat number.
_ID_LEAK_RE = re.compile(r"\b(player_id|_info_id|team_id)\s*[:=]\s*\d+\b", re.IGNORECASE)


def _redact_ids(text: str) -> str:
    return _ID_LEAK_RE.sub("[id redacted]", text)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_id: str = Field(..., min_length=1, max_length=128)


class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    grounded: bool
    unverified_numbers: list
    tools_called: list
    latency_ms: float
    error: str | None


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (chars/4) for the structured log — good enough
    for a monitoring trend line, not billing-accurate. Swap for a real
    tokenizer (tiktoken, the model provider's count endpoint) if exact
    usage is needed later."""
    return max(1, len(text) // 4)


def _log_request(request_id: str, conversation_id: str, message: str,
                  result: dict, client_ip: str) -> None:
    """One JSON line per request — query, detected intent (tools called),
    latency, token usage estimate, plus the rate-limit/decline-tracking
    signals, per Task 3's structured-logging requirement."""
    entry = {
        "timestamp": time.time(),
        "request_id": request_id,
        "conversation_id": conversation_id,
        "client_ip": client_ip,
        "query": message,
        "tools_called": result["tools_called"],
        "grounded": result["grounded"],
        "unverified_numbers": result["unverified_numbers"],
        "latency_ms": round(result["latency_ms"], 1),
        "error": result["error"],
        "est_tokens_in": _estimate_tokens(message),
        "est_tokens_out": _estimate_tokens(result["answer"]),
        "declined": _looks_declined(result["answer"]),
    }
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request):
    request_id = str(uuid.uuid4())
    client_ip = request.client.host if request.client else "unknown"

    # Task 1: rate limiting, checked against BOTH the conversation_id and
    # the client IP — either exceeding its own window rejects the request.
    if not _check_rate_limit(f"conv:{req.conversation_id}"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded for this conversation. Try again shortly.")
    if not _check_rate_limit(f"ip:{client_ip}"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded for this client. Try again shortly.")

    result = ask(_agent, req.conversation_id, req.message, _logger)

    if _looks_declined(result["answer"]):
        _decline_counts[req.conversation_id] += 1

    safe_answer = _redact_ids(result["answer"])

    _log_request(request_id, req.conversation_id, req.message, result, client_ip)

    return ChatResponse(
        response=safe_answer,
        conversation_id=req.conversation_id,
        grounded=result["grounded"],
        unverified_numbers=result["unverified_numbers"],
        tools_called=result["tools_called"],
        latency_ms=result["latency_ms"],
        error=result["error"],
    )


@app.get("/health")
def health():
    """Basic liveness check — Task 4's monitoring plan assumes this
    endpoint exists for uptime polling."""
    return {"status": "ok", "log_file": str(LOG_FILE)}


@app.get("/")
def root():
    return {
        "service": "AFL Domain-Scoped Chat Agent",
        "endpoints": {"chat": "POST /chat", "health": "GET /health"},
    }
