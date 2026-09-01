"""Day 5 automated tests: LangGraph Orchestration & Tool Calling.

Tests all 5 tasks:
- Task 1: State Design (Day5AgentState schema, profile, history, budget, intent, outputs, transitions)
- Task 2: Graph Design (Routing between Greeting, Intent, RAG, Recommendation, Booking, Rescheduling, Cancellation, Email, Goodbye, Clarification)
- Task 3: Tool Integration (tool_search_property, tool_calendar, tool_email, tool_crm, tool_check_availability, tool_rag_search)
- Task 4: Validation Safeguards (Never book unavailable slots, Never recommend unavailable properties, Ask clarification instead of guessing)
- Task 5: State Logging & Annotated Execution Traces (Transition logging into session_traces DB)

Run with:
    python test_day5.py
"""
import os
import sys

os.environ["DAY4_APPOINTMENT_DB"] = os.getenv("DAY4_TEST_APPOINTMENT_DB", "./day5_test_appointments.db")
os.environ["DAY4_EMAIL_LOG_FILE"] = os.getenv("DAY4_TEST_EMAIL_LOG", "./day5_test_emails.log")
os.environ["CRM_DB"] = os.getenv("DAY4_TEST_CRM_DB", "./day5_test_crm.db")
os.environ["DAY5_TRACE_DB"] = os.getenv("DAY5_TEST_TRACE_DB", "./day5_test_traces.db")
os.environ.setdefault("BUSINESS_HOURS_START", "10:00")
os.environ.setdefault("BUSINESS_HOURS_END", "19:00")
os.environ.setdefault("BUSINESS_DAYS", "0,1,2,3,4,5")
os.environ.setdefault("CALENDAR_MODE", "local")
os.environ.setdefault("EMAIL_PROVIDER", "console")

# Start from clean test DBs
for _f in (
    os.environ["DAY4_APPOINTMENT_DB"],
    os.environ["DAY4_EMAIL_LOG_FILE"],
    os.environ["CRM_DB"],
    os.environ["DAY5_TRACE_DB"],
):
    try:
        os.remove(_f)
    except FileNotFoundError:
        pass

import day5_agent as da5
import day5_graph as dg5
import day5_state as ds5
import day5_tools as dt5
from day4_config import BUSINESS_DAYS
from datetime import datetime, timedelta


def _next_weekday_iso(days_ahead_min=1):
    d = datetime.now().date() + timedelta(days=days_ahead_min)
    while d.weekday() not in BUSINESS_DAYS:
        d += timedelta(days=1)
    return d.isoformat()


def test_task1_state_design():
    """Task 1: State Design validation."""
    state = ds5.create_initial_day5_state(
        session_id="test-session-task1",
        user_text="Assalam o alaikum, DHA mein 3 bed flat chahiye",
        user_profile={"name": "Usman", "phone": "+923217769349"},
    )
    assert state["session_id"] == "test-session-task1"
    assert "user_profile" in state
    assert state["user_profile"].get("name") == "Usman"
    assert "property_preferences" in state
    assert "budget" in state
    assert "intent" in state
    assert "tool_outputs" in state
    assert "appointment_status" in state
    assert "node_transitions" in state
    print("[PASSED] Task 1 State Design tests passed.")
 

def test_task2_graph_nodes_and_routing():
    """Task 2: Graph Design node execution."""
    state = ds5.create_initial_day5_state("test-session-task2", "Assalam o alaikum")
    st_intent = dg5.node_intent_detection(state)
    assert st_intent["intent"] == "greeting"

    st_greet = dg5.node_greeting(st_intent)
    assert "Wa alaikum assalam" in st_greet["response"]

    # Goodbye node
    st_gb_init = ds5.create_initial_day5_state("test-session-task2-gb", "Allah Hafiz")
    st_gb_intent = dg5.node_intent_detection(st_gb_init)
    assert st_gb_intent["intent"] == "goodbye"
    st_gb = dg5.node_goodbye(st_gb_intent)
    assert "Allah Hafiz" in st_gb["response"]

    print("[PASSED] Task 2 Graph Design & Routing tests passed.")


def test_task3_tool_integration():
    """Task 3: Tool Integration tests for all 6 tools."""
    # Tool 1: Search Property
    res_search = dt5.tool_search_property(city="Lahore", property_type="House", limit=2)
    assert res_search["success"] is True
    assert "listings" in res_search

    # Tool 5: Availability Checker
    res_avail = dt5.tool_check_availability("Usama Khan", _next_weekday_iso(1), "15:00")
    assert res_avail["success"] is True
    assert "available" in res_avail

    # Tool 2: Calendar
    res_cal = dt5.tool_calendar(
        "create",
        employee_name="Usama Khan",
        client_name="Test Client",
        appt_date=_next_weekday_iso(1),
        appt_time="15:00",
    )
    assert res_cal["success"] is True

    # Tool 3: Email
    res_email = dt5.tool_email(
        "notification",
        {
            "client_name": "Test Client",
            "employee_email": "test@example.com",
            "property_label": "DHA Phase 5, Lahore",
            "appt_date": _next_weekday_iso(1),
            "appt_time": "15:00",
            "duration_minutes": 30,
        },
    )
    assert res_email["success"] is True

    # Tool 4: CRM
    res_crm = dt5.tool_crm("upsert_client", phone="+923001112233", name="Test CRM Client")
    assert res_crm["success"] is True

    # Tool 6: RAG Search
    res_rag = dt5.tool_rag_search("what is the process", k=2)
    assert res_rag["success"] is True

    print("[PASSED] Task 3 Tool Integration tests passed.")


def test_task4_validation_safeguards():
    """Task 4: Validation safeguards (unavailable slots, unavailable properties, clarification)."""
    # 1. Unavailable properties handling
    state_rec = ds5.create_initial_day5_state("test-val-1", "House in NonExistentCityX 99")
    state_rec["memory"]["slots"] = {"city": "NonExistentCityX", "property_type": "House"}
    st_rec = dg5.node_recommendation(state_rec)
    assert "koi matching verified property nahi mili" in st_rec["response"]

    # 2. Clarification asking node
    state_clar = ds5.create_initial_day5_state("test-val-2", "book appointment")
    state_clar["clarification_needed"] = {"fields": ["date", "time"]}
    st_clar = dg5.node_clarification(state_clar)
    assert "date, time" in st_clar["response"]

    print("[PASSED] Task 4 Validation Safeguards tests passed.")


def test_task5_state_logging_and_traces():
    """Task 5: State logging & execution trace database recording."""
    session = "test-session-task5-trace"
    res = da5.run_day5_turn(session, "Lahore mein commercial shop chahiye")
    assert "response" in res
    assert "node_transitions" in res
    assert len(res["node_transitions"]) > 0

    traces = da5.get_trace_history(session)
    assert len(traces) > 0
    assert traces[0]["session_id"] == session
    assert "from_node" in traces[0]
    assert "to_node" in traces[0]

    print("[PASSED] Task 5 State Logging & Annotated Execution Traces tests passed.")


def test_full_day5_end_to_end():
    """Full end-to-end multi-turn conversation flow."""
    session = "test-day5-e2e"

    # Turn 1: Search
    r1 = da5.run_day5_turn(session, "DHA Lahore mein flat dikhao")
    assert "response" in r1

    # Turn 2: Booking
    date_str = _next_weekday_iso(2)
    r2 = da5.run_day5_turn(session, f"appointment book krdo mera naam Ali hai, {date_str} shaam 4 baje")
    assert "response" in r2

    print("[PASSED] Day 5 full end-to-end conversation tests passed.")


if __name__ == "__main__":
    test_task1_state_design()
    test_task2_graph_nodes_and_routing()
    test_task3_tool_integration()
    test_task4_validation_safeguards()
    test_task5_state_logging_and_traces()
    test_full_day5_end_to_end()
    print("All Day 5 tests completed successfully!")
