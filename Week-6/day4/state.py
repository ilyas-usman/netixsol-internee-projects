"""
state.py — Week 6 / Day 4 — Task 1
===================================
State schema for the integrated chat + retrieval + prediction LangGraph app.

Design notes (Task 1 write-up):

- `messages` is the LangGraph-native conversation history (via add_messages),
  reused as-is from the Day 3 pattern so the checkpointer can persist and
  replay multi-turn threads exactly like agent.py already does.
- `intent` is a closed set of 4 categories. Every node downstream branches
  on this value with a plain Python `if`, not on free-text the LLM
  produces — that's the core of "explicit routing" (see justification
  below).
- `entities` holds whatever the router extracted (team names as typed by
  the user, not yet resolved to dataset keys — resolution happens inside
  the retrieval/prediction nodes, which is where the resolution failure
  needs to be caught anyway).
- `tool_results` accumulates the raw, un-paraphrased string/dict output of
  whichever tool or model function ran this turn. response_formatting_node
  builds the final reply FROM this list, not from an LLM's free recall of
  it — this is what makes prediction numbers and stat numbers grounded
  rather than re-generated.
- `validation_status` is set by validation_node and is what the
  conditional edge after it reads to decide: format a normal response,
  ask for clarification, or return the fallback/out-of-scope message.

Why explicit LangGraph routing instead of one free agent (Task 1
justification):

1. Consistent disclaimers on predictions are a hard product requirement
   ("predictions should always be framed as probabilistic, not certain").
   A single generic tool-calling agent decides per-turn, from a system
   prompt, whether to call a tool and how to phrase the answer — that is
   a *probabilistic* compliance mechanism (the model usually follows the
   instruction). Routing to a dedicated `prediction` branch that always
   passes through the same response_formatting_node makes the disclaimer
   structurally unconditional: it is Python control flow, not prompt
   compliance, so it cannot be skipped by a model having an off turn.
2. Prediction and retrieval need genuinely different validation. A
   retrieval NOT_FOUND and a prediction "unknown team" ValueError need
   different clarification questions and different fallback copy. A
   single agent has to get all of that right inside one system prompt,
   for every tool, every time; a router+validation_node pair only has to
   get it right once per branch.
3. Cost/latency: the router does ONE structured-output call and then goes
   straight to a plain Python function call (predict.py / tools.py) — no
   second LLM call deciding "should I call a tool, which one, with what
   args" the way a ReAct-style agent loop does. Fewer LLM calls in the
   loop means fewer chances for the model to misfire on a numeric/team
   argument.
4. Off-topic handling is guaranteed rather than best-effort. A generic
   agent has to remember, every turn, to check "is this AFL at all" before
   reasoning further. Here it's a graph branch that can never reach a
   tool call.
"""
from __future__ import annotations

from typing import Annotated, Literal, Optional, TypedDict
from langgraph.graph.message import add_messages

Intent = Literal["retrieval", "prediction", "factual", "off_topic"]
ValidationStatus = Literal["ok", "needs_clarification", "out_of_scope", "error"]


class AgentState(TypedDict, total=False):
    # --- conversation ---
    messages: Annotated[list, add_messages]   # LangGraph chat history (checkpointed per thread_id)
    user_query: str                           # this turn's raw user text

    # --- router output ---
    intent: Intent
    intent_reasoning: str
    entities: dict                            # router-extracted args, NOT yet resolved to dataset keys

    # --- tool / model execution ---
    tool_results: list[str]                   # raw grounding evidence for this turn
    prediction_payload: Optional[dict]         # structured predict.py output, if intent == "prediction"

    # --- validation / fallback ---
    validation_status: ValidationStatus
    validation_message: Optional[str]
    clarification_question: Optional[str]

    # --- output ---
    final_response: str
    thread_id: str
