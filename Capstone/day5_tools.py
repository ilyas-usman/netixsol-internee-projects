"""Week 7 Day 5 — Task 3: Tool Integration.

Wraps the 6 core application capabilities into explicit python tools:
1. Search Property (tool_search_property)
2. Calendar (tool_calendar)
3. Email (tool_email)
4. CRM (tool_crm)
5. Availability Checker (tool_check_availability)
6. RAG Search (tool_rag_search)
"""
from __future__ import annotations

import logging
from typing import Any

import appointment_agent as aa
import appointment_store as appt_store
import calendar_service
import crm_store
import email_service
from day4_config import APPOINTMENT_DURATION_MINUTES
from rag_pipeline import chunk_documents, get_collection, index_chunks, load_documents, retrieve
from structured_retrieval import enrich_listing_rows, query_commercial, query_properties

_log = logging.getLogger("day5_tools")

# Initialize RAG collection once for tool_rag_search
_docs = load_documents("./knowledge_docs")
_chunks = chunk_documents(_docs, chunk_size=400)
if _chunks:
    _collection = get_collection(reset=False)
    if _collection.count() == 0:
        _collection = index_chunks(_chunks, reset=False)
else:
    _collection = None


def tool_search_property(
    city: str | None = None,
    location: str | None = None,
    exclude_location: str | None = None,
    property_type: str | None = None,
    unit_type: str | None = None,
    purpose: str | None = None,
    max_price: float | int | None = None,
    bedrooms: int | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Tool 1: Search Property — queries residential and commercial property databases."""
    try:
        commercial_terms = ("shop", "office", "warehouse", "plaza", "commercial")
        is_commercial = bool(
            unit_type
            or (property_type and any(t in property_type.lower() for t in commercial_terms))
        )

        if is_commercial:
            rows = query_commercial(
                city=city,
                location=location,
                exclude_location=exclude_location,
                unit_type=unit_type or property_type,
                purpose=purpose or "For Sale",
                max_price=max_price,
                limit=limit,
            )
            kind = "commercial"
        else:
            rows = query_properties(
                city=city,
                location=location,
                exclude_location=exclude_location,
                purpose=purpose or "For Sale",
                max_price=max_price,
                bedrooms=bedrooms,
                property_type=property_type,
                limit=limit,
            )
            kind = "residential"

        enriched = enrich_listing_rows(rows)
        return {
            "success": True,
            "count": len(enriched),
            "kind": kind,
            "listings": enriched,
            "filters_applied": {
                "city": city, "location": location, "exclude_location": exclude_location,
                "property_type": property_type, "unit_type": unit_type,
                "purpose": purpose, "max_price": max_price, "bedrooms": bedrooms,
            },
        }
    except Exception as exc:
        _log.error("tool_search_property error: %s", exc)
        return {"success": False, "error": str(exc), "listings": []}


def tool_check_availability(
    employee_name: str,
    appt_date: str,
    appt_time: str,
    duration_minutes: int = APPOINTMENT_DURATION_MINUTES,
    exclude_appt_id: str | None = None,
) -> dict[str, Any]:
    """Tool 5: Availability Checker — checks employee schedule and double booking."""
    try:
        ok, reason = aa._within_business_hours(appt_date, appt_time)
        if not ok:
            return {"success": True, "available": False, "reason": reason, "next_available_slot": None}

        calendar = calendar_service.get_calendar_provider()
        try:
            free = calendar.is_slot_free(
                employee_name, appt_date, appt_time, duration_minutes, exclude_appt_id=exclude_appt_id
            )
        except Exception as exc:
            _log.warning("Calendar availability check failed: %s", exc)
            free = None  # Unknown calendar status

        next_slot = None
        if free is False:
            next_slot = aa._next_available_slot(employee_name, appt_date, appt_time)

        return {
            "success": True,
            "available": free is True,
            "calendar_provider": calendar.name,
            "employee_name": employee_name,
            "appt_date": appt_date,
            "appt_time": appt_time,
            "next_available_slot": next_slot,
        }
    except Exception as exc:
        _log.error("tool_check_availability error: %s", exc)
        return {"success": False, "available": False, "error": str(exc)}


def tool_calendar(
    action: str,
    appointment_id: str | None = None,
    employee_name: str | None = None,
    employee_email: str | None = None,
    client_name: str | None = None,
    client_phone: str | None = None,
    property_label: str | None = None,
    appt_date: str | None = None,
    appt_time: str | None = None,
    duration_minutes: int = APPOINTMENT_DURATION_MINUTES,
    notes: str = "",
) -> dict[str, Any]:
    """Tool 2: Calendar — manages Google/Local calendar event creation, update, deletion."""
    try:
        calendar = calendar_service.get_calendar_provider()
        if action == "create":
            event = calendar.create_event(
                employee_name=employee_name,
                employee_email=employee_email,
                client_name=client_name,
                client_phone=client_phone,
                property_label=property_label,
                appt_date=appt_date,
                appt_time=appt_time,
                duration_minutes=duration_minutes,
                notes=notes,
            )
            return {"success": True, "event_id": event.get("event_id"), "provider": calendar.name}

        elif action == "update":
            event = calendar.update_event(
                appointment_id,
                employee_name=employee_name,
                employee_email=employee_email,
                client_name=client_name,
                client_phone=client_phone,
                property_label=property_label,
                appt_date=appt_date,
                appt_time=appt_time,
                duration_minutes=duration_minutes,
                notes=notes,
            )
            return {"success": True, "event_id": event.get("event_id"), "provider": calendar.name}

        elif action == "delete":
            ok = calendar.delete_event(appointment_id)
            return {"success": ok, "provider": calendar.name}

        else:
            return {"success": False, "error": f"Unknown calendar action: {action}"}
    except Exception as exc:
        _log.error("tool_calendar error: %s", exc)
        return {"success": False, "error": str(exc)}


def tool_email(
    action: str,
    appointment: dict[str, Any],
    old_date: str | None = None,
    old_time: str | None = None,
) -> dict[str, Any]:
    """Tool 3: Email — dispatches notification, reschedule, cancellation, and confirmation emails."""
    try:
        if action == "notification":
            res = email_service.send_employee_notification(appointment)
        elif action == "reschedule_notice":
            res = email_service.send_employee_reschedule_notice(appointment, old_date or "", old_time or "")
        elif action == "cancellation_notice":
            res = email_service.send_employee_cancellation_notice(appointment)
        elif action == "client_confirmation":
            res = email_service.send_client_confirmation(appointment)
        else:
            return {"success": False, "error": f"Unknown email action: {action}"}
        return {"success": True, "result": res}
    except Exception as exc:
        _log.error("tool_email error: %s", exc)
        return {"success": False, "error": str(exc)}


def tool_crm(
    action: str,
    phone: str | None = None,
    name: str | None = None,
    email: str | None = None,
    preferences: dict | None = None,
    due_date: str | None = None,
    note: str = "",
    session_id: str | None = None,
    appointment_id: str | None = None,
) -> dict[str, Any]:
    """Tool 4: CRM — client profile management, session linking, reminders."""
    try:
        if action == "get_client":
            client = crm_store.get_client(phone)
            return {"success": True, "client": client}

        elif action == "upsert_client":
            client = crm_store.upsert_client(phone, name=name, email=email)
            if preferences:
                crm_store.merge_preferences(phone, preferences)
                client = crm_store.get_client(phone)
            return {"success": True, "client": client}

        elif action == "merge_preferences":
            crm_store.merge_preferences(phone, preferences or {})
            return {"success": True, "phone": phone}

        elif action == "create_reminder":
            reminder = crm_store.create_reminder(
                client_phone=phone, session_id=session_id, appointment_id=appointment_id,
                due_date=due_date, note=note, created_by="tool_crm",
            )
            return {"success": True, "reminder": reminder}

        elif action == "get_profile":
            profile = crm_store.get_client_profile(phone)
            return {"success": True, "profile": profile}

        else:
            return {"success": False, "error": f"Unknown CRM action: {action}"}
    except Exception as exc:
        _log.error("tool_crm error: %s", exc)
        return {"success": False, "error": str(exc)}


def tool_rag_search(query: str, k: int = 4) -> dict[str, Any]:
    """Tool 6: RAG Search — retrieves relevant knowledge documents."""
    try:
        if not _collection:
            return {"success": True, "hits": [], "count": 0}
        hits = retrieve(query, _collection, k=k)
        return {"success": True, "hits": hits, "count": len(hits)}
    except Exception as exc:
        _log.error("tool_rag_search error: %s", exc)
        return {"success": False, "error": str(exc), "hits": []}
