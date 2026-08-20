"""
graph.py — Week 6 / Day 4 — Task 1 (graph sketch, executable)
=================================================================

                                   +------------------+
                                   |   router_node    |
                                   | (intent + entity |
                                   |   extraction)     |
                                   +---------+--------+
                                             |
                 +---------------+----------+----------+---------------+
                 |               |                     |               |
                 v               v                     v               v
         retrieval_node   prediction_node        factual_node    off_topic_node
                 |               |                     |               |
                 +-------+-------+                     |               |
                         v                              |               |
                  validation_node                       |               |
                    |         |                         |               |
        (ok) -------+         +----- (needs_clarification /             |
             |                        out_of_scope / error)             |
             |                              |                           |
             v                              v                           |
   response_formatting_node      clarification_node                     |
             |                              |                           |
             +--------------- END <---------+-----------<---------------+
                                (via response_formatting_node for
                                 factual/off_topic, which have no
                                 tool call to validate)

Only retrieval_node and prediction_node feed into validation_node --
factual_node and off_topic_node have no tool output to validate (no
numbers, no dataset lookup), so they go straight to response_formatting_node.
This is itself a deliberate scoping choice: don't run a validation step
that has nothing to check, since that would just be structural noise in the
trace without changing the outcome (Task 5's logs should show every step
doing real work).
"""
from __future__ import annotations

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver

from state import AgentState
from router import router_node
from graph_nodes import (
    retrieval_node, prediction_node, factual_node, off_topic_node,
    validation_node, clarification_node, response_formatting_node,
)


def _route_from_router(state: AgentState) -> str:
    return state["intent"]  # "retrieval" | "prediction" | "factual" | "off_topic"


def _route_from_validation(state: AgentState) -> str:
    status = state.get("validation_status")
    if status == "ok":
        return "response_formatting_node"
    return "clarification_node"  # needs_clarification, out_of_scope, and error all surface as a question/explanation


def build_graph():
    g = StateGraph(AgentState)

    g.add_node("router_node", router_node)
    g.add_node("retrieval_node", retrieval_node)
    g.add_node("prediction_node", prediction_node)
    g.add_node("factual_node", factual_node)
    g.add_node("off_topic_node", off_topic_node)
    g.add_node("validation_node", validation_node)
    g.add_node("clarification_node", clarification_node)
    g.add_node("response_formatting_node", response_formatting_node)

    g.add_edge(START, "router_node")
    g.add_conditional_edges("router_node", _route_from_router, {
        "retrieval": "retrieval_node",
        "prediction": "prediction_node",
        "factual": "factual_node",
        "off_topic": "off_topic_node",
    })

    g.add_edge("retrieval_node", "validation_node")
    g.add_edge("prediction_node", "validation_node")
    g.add_conditional_edges("validation_node", _route_from_validation, {
        "response_formatting_node": "response_formatting_node",
        "clarification_node": "clarification_node",
    })

    g.add_edge("factual_node", "response_formatting_node")
    g.add_edge("off_topic_node", "response_formatting_node")

    g.add_edge("clarification_node", END)
    g.add_edge("response_formatting_node", END)

    checkpointer = InMemorySaver()
    return g.compile(checkpointer=checkpointer)


def ask(app, thread_id: str, user_query: str) -> dict:
    """Run one turn. Returns the full final state (so callers/tests can
    inspect intent, tool_results, validation_status, etc. -- not just the
    final_response text)."""
    config = {"configurable": {"thread_id": thread_id}}
    result = app.invoke(
        {"user_query": user_query, "messages": [{"role": "user", "content": user_query}]},
        config=config,
    )
    # append the assistant's reply to the thread's message history so
    # multi-turn context (used by the router's recent_context) accumulates
    app.update_state(config, {"messages": [{"role": "assistant", "content": result["final_response"]}]})
    return result


if __name__ == "__main__":
    app = build_graph()
    thread = "demo-thread"
    demo_turns = [
        "What were Marcus Bontempelli's stats in round 11, 2025?",
        "Who will win Collingwood vs Geelong this week?",
        "Who's going to top-score for the Cats this week?",
        "What's the capital of France?",
        "How's Bontempelli going this year?",
    ]
    for t in demo_turns:
        print(f"\nUSER: {t}")
        r = ask(app, thread, t)
        print(f"INTENT: {r.get('intent')}")
        print(f"AGENT: {r['final_response']}")
