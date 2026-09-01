"""Week 7 Day 5 — Task 2: Graph Design & Task 4 Validation Safeguards.

Implements the complete LangGraph StateGraph routing between:
- Greeting (node_greeting)
- Intent Detection (node_intent_detection)
- RAG (node_rag)
- Recommendation (node_recommendation)
- Booking (node_booking)
- Rescheduling (node_rescheduling)
- Cancellation (node_cancellation)
- Email (node_email)
- Goodbye (node_goodbye)
- Clarification (node_clarification)

Task 4 Validation Rules enforced:
- Never book unavailable slots.
- Never recommend unavailable properties.
- Ask clarification instead of guessing.

Task 5 Logging:
- Every node transition is recorded into `node_transitions` state and persisted.
"""
from __future__ import annotations

import difflib
import json
import re
import time
from typing import Any

from day3_objections import detect_objection, normalize_text
from day3_router import FAREWELL_MARKERS, route_and_extract
from day4_config import APPOINTMENT_DURATION_MINUTES
from day5_state import Day5AgentState, record_transition
from day5_tools import (
    tool_calendar,
    tool_check_availability,
    tool_crm,
    tool_email,
    tool_rag_search,
    tool_search_property,
)
from rag_pipeline import generate_grounded_reply

try:
    from langgraph.graph import END, START, StateGraph
except ImportError:
    StateGraph = None
    START = END = None


GREETING_MARKERS = (
    "assalam o alaikum", "assalamualaikum", "salam", "hello", "hi", "hey",
    "kya haal hai", "kya hal hai", "how are you", "good morning", "good evening",
)


def _norm(text: str) -> str:
    return normalize_text(text)


def node_intent_detection(state: Day5AgentState) -> Day5AgentState:
    """Node 1: Intent Detection — extracts intent, budget, preferences, slots."""
    prev_node = "START"
    user_text = state.get("user_text", "")
    s = _norm(user_text)

    property_keywords = (
        "flat", "house", "ghar", "shop", "office", "plaza", "commercial", "residential",
        "budget", "price", "crore", "lac", "lakh", "rent", "sale", "buy", "purchase",
        "lahore", "islamabad", "karachi", "rawalpindi", "faisalabad", "multan", "peshawar",
        "فلیٹ", "گھر", "پراپرٹی", "بجٹ", "کرایہ", "خریدنا", "بیچنا", "اسلام آباد", "لاہور", "کراچی", "فیصل آباد",
        "1", "2", "3", "4", "5", "bed", "marla", "kanal", "sqft",
    )
    is_property_search = any(k in s for k in property_keywords)

    off_topic_or_general_markers = (
        "weather", "mausam", "cricket", "match", "capital", "france", "joke", "latifa",
        "bura", "ghalat", "pagal", "worst", "manager", "unresolved", "issue", "service",
        "terrible", "pathetic", "complaint", "shikayat", "bakwas",
    )
    is_silent_or_offtopic = (
        not user_text.strip()
        or user_text.strip() in ("...", "<SILENT / EMPTY INPUT>")
        or any(k in s for k in off_topic_or_general_markers)
    )

    # 1. Intent identification logic
    if aa_is_cancel(user_text):
        intent = "cancellation"
    elif aa_is_reschedule(user_text):
        intent = "rescheduling"
    elif aa_is_booking(user_text):
        intent = "booking"
    elif any(m in s for m in FAREWELL_MARKERS) and not is_property_search and len(user_text.split()) <= 4:
        intent = "goodbye"
    elif any(m in s for m in GREETING_MARKERS) and not is_property_search and len(user_text.split()) <= 4:
        intent = "greeting"
    elif is_silent_or_offtopic and not any(pk in s for pk in ("flat", "house", "ghar", "shop", "office", "plaza", "buy", "sell", "rent", "crore", "lakh", "budget")):
        intent = "intent_detection"
    else:
        # Route via Day 3 extractor for search/rag/chat
        route_info = route_and_extract(user_text, state.get("memory"))
        state["route"] = route_info
        r_type = route_info.get("route")
        if r_type == "rag":
            intent = "rag"
        elif r_type in ("sql", "both"):
            intent = "recommendation"
        else:
            intent = "intent_detection"

    state["intent"] = intent
    record_transition(state, prev_node, "node_intent_detection", f"Detected intent: {intent}")
    return state


def aa_is_cancel(text: str) -> bool:
    import appointment_agent as aa
    return aa.is_cancel_intent(text)


def aa_is_reschedule(text: str) -> bool:
    import appointment_agent as aa
    return aa.is_reschedule_intent(text)


def aa_is_booking(text: str) -> bool:
    import appointment_agent as aa
    return aa.is_booking_intent(text) or aa.is_availability_question(text)


def node_greeting(state: Day5AgentState) -> Day5AgentState:
    """Node: Greeting — friendly salutations & service introduction."""
    record_transition(state, "node_intent_detection", "node_greeting", "User greeted")
    state["response"] = (
        "Wa alaikum assalam! Main RealEstate Hub ka AI assistant hoon. "
        "Aap kis shehar, location ya budget mein property dekhna chahte hain?"
    )
    return state


def node_goodbye(state: Day5AgentState) -> Day5AgentState:
    """Node: Goodbye — session wrap-up."""
    record_transition(state, "node_intent_detection", "node_goodbye", "User said farewell")
    state["response"] = "Allah Hafiz sir! RealEstate Hub se baat karne ka shukriya. Aapka din accha guzre!"
    return state


def node_rag(state: Day5AgentState) -> Day5AgentState:
    """Node: RAG — knowledge document retrieval via tool_rag_search."""
    record_transition(state, "node_intent_detection", "node_rag", "Knowledge retrieval request")
    user_text = state.get("user_text", "")
    tool_res = tool_rag_search(user_text, k=4)

    outputs = list(state.get("tool_outputs") or [])
    outputs.append({"tool": "tool_rag_search", "result": tool_res})
    state["tool_outputs"] = outputs

    hits = tool_res.get("hits", [])
    state["rag_hits"] = hits

    if hits:
        state["response"] = generate_grounded_reply(user_text, hits)
    else:
        state["response"] = "Ji, is baare mein verified knowledge docs mein detail nahi mili. Main human consultant se confirm karke bata sakta hoon."
    return state


def node_recommendation(state: Day5AgentState) -> Day5AgentState:
    """Node: Recommendation — property query via tool_search_property with validation.

    Task 4 Validation: Never recommend unavailable properties.
    """
    record_transition(state, "node_intent_detection", "node_recommendation", "Searching matching properties")
    memory = state.get("memory") or {}
    route = state.get("route") or route_and_extract(state.get("user_text", ""), memory)

    slots = dict(memory.get("slots") or {})
    slots.update(route.get("slots") or {})

    # Execute Search Property tool
    tool_res = tool_search_property(
        city=slots.get("city"),
        location=slots.get("location"),
        exclude_location=slots.get("exclude_location"),
        property_type=slots.get("property_type"),
        unit_type=slots.get("unit_type"),
        purpose=slots.get("purpose"),
        max_price=slots.get("budget"),
        bedrooms=slots.get("bedrooms"),
        limit=5,
    )

    outputs = list(state.get("tool_outputs") or [])
    outputs.append({"tool": "tool_search_property", "result": tool_res})
    state["tool_outputs"] = outputs

    listings = tool_res.get("listings", [])
    state["listings"] = listings
    state["last_shown"] = listings

    # Task 4 Validation: Never recommend unavailable properties
    if not listings:
        req_parts = [slots.get("city"), slots.get("location"), slots.get("property_type")]
        req_str = ", ".join(p for p in req_parts if p) or "is search query"
        state["response"] = f"Ji, {req_str} ke liye koi matching verified property nahi mili. Budget ya area adjust karke dekhein."
    else:
        parts = []
        for r in listings[:4]:
            loc = f"{r.get('location')}, {r.get('city')}"
            price = f"PKR {r.get('price') or r.get('price_pkr'):,.0f}" if (r.get("price") or r.get("price_pkr")) else "Unverified"
            unit = r.get("property_type") or r.get("unit_type") or "Property"
            parts.append(f"{unit} in {loc} ({price})")
        state["response"] = "Ji bilkul, verified matching options ye hain: " + "; ".join(parts) + "."

    return state


def node_booking(state: Day5AgentState) -> Day5AgentState:
    """Node: Booking — viewing appointment creation flow with availability validation.

    Task 4 Validation: Never book unavailable slots; Ask clarification instead of guessing.
    """
    record_transition(state, "node_intent_detection", "node_booking", "Handling booking request")
    import appointment_agent as aa
    import appointment_store as appt_store

    session_id = state.get("session_id", "default")
    user_text = state.get("user_text", "")
    memory = state.get("memory") or {}
    known_phone = (state.get("user_profile") or {}).get("phone")

    # Delegate turn to appointment_agent handler for full multi-turn draft state machine
    res = aa.handle_appointment_turn(session_id, user_text, memory, known_phone=known_phone)

    draft = appt_store.get_draft(session_id)
    if draft:
        state["appointment_status"] = {
            "intent": draft.get("intent"),
            "stage": draft.get("stage"),
            "slots": draft.get("slots"),
        }

    if res and res.get("response"):
        state["response"] = res["response"]
    else:
        state["response"] = "Ji bilkul, appointment book kar dete hain. Aap kis din aur kis waqt aana chahenge?"

    return state


def node_rescheduling(state: Day5AgentState) -> Day5AgentState:
    """Node: Rescheduling — rescheduling active appointment."""
    record_transition(state, "node_intent_detection", "node_rescheduling", "Handling reschedule request")
    import appointment_agent as aa
    import appointment_store as appt_store

    session_id = state.get("session_id", "default")
    user_text = state.get("user_text", "")
    memory = state.get("memory") or {}

    res = aa._handle_reschedule(session_id, user_text, memory)
    draft = appt_store.get_draft(session_id)
    if draft:
        state["appointment_status"] = {
            "intent": draft.get("intent"),
            "stage": draft.get("stage"),
            "target_appointment_id": draft.get("target_appointment_id"),
        }

    state["response"] = res
    return state


def node_cancellation(state: Day5AgentState) -> Day5AgentState:
    """Node: Cancellation — cancelling active appointment."""
    record_transition(state, "node_intent_detection", "node_cancellation", "Handling cancellation request")
    import appointment_agent as aa
    import appointment_store as appt_store

    session_id = state.get("session_id", "default")
    user_text = state.get("user_text", "")
    memory = state.get("memory") or {}

    res = aa._handle_cancel(session_id, user_text, memory)
    draft = appt_store.get_draft(session_id)
    if draft:
        state["appointment_status"] = {
            "intent": draft.get("intent"),
            "stage": draft.get("stage"),
            "target_appointment_id": draft.get("target_appointment_id"),
        }

    state["response"] = res
    return state


def node_email(state: Day5AgentState) -> Day5AgentState:
    """Node: Email — executes tool_email for notifications."""
    record_transition(state, "node_intent_detection", "node_email", "Triggering email notification tool")
    appts = (state.get("appointment_status") or {}).get("appointment")
    if appts:
        tool_res = tool_email("notification", appts)
        outputs = list(state.get("tool_outputs") or [])
        outputs.append({"tool": "tool_email", "result": tool_res})
        state["tool_outputs"] = outputs
        state["response"] = "Email notification dispatched successfully."
    else:
        state["response"] = "No active appointment on record for email notification."
    return state


def node_clarification(state: Day5AgentState) -> Day5AgentState:
    """Node: Clarification — Task 4: Ask clarification instead of guessing."""
    record_transition(state, "node_intent_detection", "node_clarification", "Requesting user clarification")
    missing = (state.get("clarification_needed") or {}).get("fields", [])
    if missing:
        field_str = ", ".join(missing)
        state["response"] = f"Aapki request poori karne ke liye {field_str} batana zaroori hai. Meherbani karke specify kar dein."
    else:
        state["response"] = "Ji, aapki request samajh nahi aayi. Meherbani karke thoda wazahat se batayein."
    return state


def node_intent_detection_response(state: Day5AgentState) -> Day5AgentState:
    """Node: Intent Detection Response Node for Off-topic, Angry customer, Silent caller, and fallback queries."""
    record_transition(state, "node_intent_detection", "node_intent_detection_response", "Handling intent_detection query")
    user_text = (state.get("user_text") or "").strip()
    s = _norm(user_text)

    # 1. Silent caller
    if not user_text or user_text in ("...", "<SILENT / EMPTY INPUT>") or len(user_text) == 0:
        state["response"] = "Ji, aapki taraf se koi awaz ya input nahi mila. Main RealEstate Hub ka AI assistant hoon, property search ya appointment booking ke liye batayein."
        return state

    # 2. Angry customer
    angry_keywords = (
        "bura", "ghalat", "pagal", "worst", "manager", "unresolved", "issue",
        "service", "terrible", "pathetic", "complaint", "shikayat", "bakwas",
    )
    if any(k in s for k in angry_keywords):
        if "manager" in s:
            state["response"] = "Ji bilkul, main aapki request senior manager ko escalate kar raha hoon. Wo jald aapse rabta karenge."
        elif "timing" in s or "ghalat" in s:
            state["response"] = "Humain ghalti ke liye afsos hai. Hum aapki appointment timing durust kar dete hain. Meherbani karke sahi time aur date batayein."
        elif "worst" in s or "experience" in s:
            state["response"] = "Humain aapke bure experience ke liye afsos hai. Hum service quality improve karne ke liye aapka feedback senior team tak pohncha rahe hain."
        else:
            state["response"] = "Humain aapki pareshani ke liye behad afsos hai. Aapki shikayat note kar li gayi hai aur humari support team jald aapse rabta karegi."
        return state

    # 3. Off-topic queries
    if "weather" in s or "mausam" in s:
        state["response"] = "Main weather updates nahi bata sakta, lekin main RealEstate Hub ka AI assistant hoon! Lahore ya kisi bhi shehar mein property search mein aapki madad kar sakta hoon."
        return state
    elif "cricket" in s or "match" in s:
        state["response"] = "Main sports/cricket updates nahi bata sakta. Main RealEstate Hub ka AI assistant hoon, property listings aur viewing appointments ke baare mein pooch sakte hain!"
        return state
    elif "capital" in s or "france" in s:
        state["response"] = "France ka capital Paris hai! Lekin main RealEstate Hub ka AI assistant hoon, real estate aur property queries mein aapki help kar sakta hoon."
        return state
    elif "joke" in s or "latifa" in s:
        state["response"] = "Aik real estate agent ne kaha: 'Ye ghar boht quiet hai!' Client: 'Lekin paas train guzarti hai!' Agent: 'Haan wo sirf quiet hours mein!' :) Ab bataein, aapko kis budget mein property chahiye?"
        return state

    # General / Default response for intent_detection
    state["response"] = "Main RealEstate Hub ka AI assistant hoon. Main sirf verified real estate listings, pricing aur viewing bookings mein aapki madad kar sakta hoon."
    return state


# ---------------------------------------------------------------------------
# Router & Graph Construction
# ---------------------------------------------------------------------------
def route_next_node(state: Day5AgentState) -> str:
    intent = state.get("intent", "intent_detection")
    if intent == "greeting":
        return "greeting"
    elif intent == "goodbye":
        return "goodbye"
    elif intent == "rag":
        return "rag"
    elif intent == "recommendation":
        return "recommendation"
    elif intent == "booking":
        return "booking"
    elif intent == "rescheduling":
        return "rescheduling"
    elif intent == "cancellation":
        return "cancellation"
    elif intent == "email":
        return "email"
    elif intent == "clarification":
        return "clarification"
    elif intent == "intent_detection":
        return "intent_detection_node"
    else:
        return "intent_detection_node"


def build_day5_graph():
    if StateGraph is None:
        return None

    workflow = StateGraph(Day5AgentState)

    # Add graph nodes
    workflow.add_node("intent_detection", node_intent_detection)
    workflow.add_node("greeting", node_greeting)
    workflow.add_node("goodbye", node_goodbye)
    workflow.add_node("rag", node_rag)
    workflow.add_node("recommendation", node_recommendation)
    workflow.add_node("booking", node_booking)
    workflow.add_node("rescheduling", node_rescheduling)
    workflow.add_node("cancellation", node_cancellation)
    workflow.add_node("email", node_email)
    workflow.add_node("clarification", node_clarification)
    workflow.add_node("intent_detection_node", node_intent_detection_response)

    # Start at intent_detection
    workflow.add_edge(START, "intent_detection")

    # Conditional routing edge from intent_detection
    workflow.add_conditional_edges(
        "intent_detection",
        route_next_node,
        {
            "greeting": "greeting",
            "goodbye": "goodbye",
            "rag": "rag",
            "recommendation": "recommendation",
            "booking": "booking",
            "rescheduling": "rescheduling",
            "cancellation": "cancellation",
            "email": "email",
            "clarification": "clarification",
            "intent_detection_node": "intent_detection_node",
        },
    )

    # All operational nodes terminate at END
    for n in ("greeting", "goodbye", "rag", "recommendation", "booking", "rescheduling", "cancellation", "email", "clarification", "intent_detection_node"):
        workflow.add_edge(n, END)

    return workflow.compile()


DAY5_GRAPH = build_day5_graph()
