"""FastAPI entrypoint for Week 7 Day 3."""
from __future__ import annotations
import asyncio, json, logging, os, time, uuid
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from conversation_memory import get_state, reset_session
from day3_agent import run_turn
from evaluation_harness import save_turn, objection_test_report, score_call, get_evaluation_history
from day3_config import STT_PROVIDER, TTS_PROVIDER, VOICE_MODE, VAPI_PUBLIC_KEY, VAPI_ASSISTANT_ID, VAPI_FIRST_MESSAGE
from voice_pipeline import run_voice_text_turn
from stt_providers import deepgram_transcripts

# Week 7 Day 4 addition: used only for the temporary Vapi caller-ID
# diagnostic log in vapi_chat_completions() below.
_vapi_log = logging.getLogger("vapi_chat_completions")

app=FastAPI(title="RealEstate Hub — Week 7 Day 3 Voice Agent", version="3.0.0")

class TextTurn(BaseModel):
    session_id: str
    message: str


class EvaluationScore(BaseModel):
    call_id: str
    scores: dict[str, int]
    notes: str = ""

@app.get("/health")
def health():
        return {"status":"ok","day":3,"stt_provider":STT_PROVIDER,
            "tts_provider":TTS_PROVIDER,
            "voice_mode":VOICE_MODE,
            "voice_provider":"vapi" if VAPI_PUBLIC_KEY else TTS_PROVIDER}


@app.get("/api/config")
def client_config():
    """Expose browser-safe Vapi settings; never expose provider secret keys."""
    return {"vapi_public_key": VAPI_PUBLIC_KEY,
            "vapi_assistant_id": VAPI_ASSISTANT_ID,
            "vapi_first_message": VAPI_FIRST_MESSAGE}

@app.post("/api/chat")
def chat(req: TextTurn):
    started=time.perf_counter()
    result=run_turn(req.session_id, req.message)
    result["timings"]["api_total_ms"]=(time.perf_counter()-started)*1000
    save_turn(req.session_id, req.message, result["response"], result["timings"])
    return {
        "session_id":req.session_id,
        "response":result["response"],
        "listings":result.get("listings", []),
        "route":result["route"],
        "slots":result["memory"]["slots"],
        "objection":result.get("objection_category"),
        "escalation":result.get("escalation",False),
        "timings":result["timings"],
    }


@app.post("/api/vapi/property-search")
def vapi_property_search(payload: dict):
    """Vapi custom tool endpoint for grounded property conversations."""
    message = payload.get("message", payload)
    calls = message.get("toolCallList", [])
    results = []

    for call in calls:
        arguments = call.get("arguments") or call.get("function", {}).get("parameters", {})
        session_id = arguments.get("session_id") or message.get("call", {}).get("id", "vapi-default")
        query = arguments.get("query") or arguments.get("message") or arguments.get("text", "")
        if not query:
            tool_result = {"error": "A property search query is required."}
        else:
            result = run_turn(session_id, query)
            tool_result = {
                "response": result["response"],
                "listings": result.get("listings", []),
                "slots": result["memory"]["slots"],
                "objection": result.get("objection_category", "none"),
            }
        results.append({"toolCallId": call.get("id", ""), "result": tool_result})

    return {"results": results}


@app.post("/v1/chat/completions")
@app.post("/chat/completions")
async def vapi_chat_completions(req: dict):
    """OpenAI-compatible endpoint for Vapi Custom LLM calls on app_day3."""
    model_name = req.get("model", "custom-llm")
    stream_mode = req.get("stream", False)
    messages = req.get("messages", [])

    user_query = ""
    if isinstance(messages, list):
        for msg in reversed(messages):
            if isinstance(msg, dict) and msg.get("role") == "user":
                content = msg.get("content")
                if isinstance(content, str) and content.strip():
                    user_query = content.strip()
                    break
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("text"):
                            user_query = block.get("text").strip()
                            break
                    if user_query:
                        break

    if not user_query:
        user_query = "Assalam-o-Alaikum"

    call_id = req.get("call", {}).get("id") or req.get("id") or "vapi-default-session"

    # FIX (requested after real Vapi call testing): on a real phone call,
    # asking the client to speak their phone number digit-by-digit is
    # error-prone for STT and awkward to record. Vapi includes the actual
    # caller's number in the call metadata for real phone calls — use that
    # automatically instead of ever asking for it. Checked defensively in
    # a couple of plausible payload shapes; if none match (e.g. a web/test
    # call with no real caller ID, or a different Vapi payload layout than
    # expected), this is simply None and the assistant falls back to
    # asking normally, exactly as before.
    call_obj = req.get("call", {}) if isinstance(req.get("call"), dict) else {}
    customer_obj = call_obj.get("customer") or req.get("customer") or {}
    known_phone = None
    if isinstance(customer_obj, dict):
        raw_number = customer_obj.get("number")
        if raw_number:
            known_phone = raw_number

    # DIAGNOSTIC (temporary — safe to remove once caller-ID extraction is
    # confirmed working on a real call): a real test showed known_phone
    # stayed None even on what should have been a caller-ID-bearing call,
    # meaning the actual Vapi payload shape differs from what's assumed
    # above. Logs only the "call" key (never the full conversation) so the
    # real structure is visible in the server console on the next call —
    # this never changes behavior, only visibility.
    if known_phone is None:
        _vapi_log.warning("known_phone not found this turn — raw 'call' key: %s", json.dumps(call_obj, ensure_ascii=False)[:2000])

    try:
        result = run_turn(call_id, user_query, known_phone=known_phone)
        reply_text = result.get("response", "Assalam o alaikum sir! Main RealEstate Hub se hoon. Aap ki kya requirement hai?")
    except Exception as e:
        reply_text = "Ji bilkul sir, main Real Estate Hub se baat kar raha hoon. Aap ki kya requirement hai?"

    if stream_mode:
        from fastapi.responses import StreamingResponse
        async def sse_gen():
            ts = int(time.time())
            chunk_id = f"chatcmpl-vapi-{ts}"
            c1 = {"id": chunk_id, "object": "chat.completion.chunk", "created": ts, "model": model_name, "choices": [{"index": 0, "delta": {"role": "assistant", "content": reply_text}, "finish_reason": None}]}
            yield f"data: {json.dumps(c1)}\n\n"
            c2 = {"id": chunk_id, "object": "chat.completion.chunk", "created": ts, "model": model_name, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
            yield f"data: {json.dumps(c2)}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(sse_gen(), media_type="text/event-stream")

    return {
        "id": f"chatcmpl-vapi-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_name,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": reply_text},
                "finish_reason": "stop"
            }
        ],
        "usage": {"prompt_tokens": 50, "completion_tokens": 50, "total_tokens": 100}
    }

@app.get("/api/memory/{session_id}")
def memory(session_id: str):
    return get_state(session_id)

@app.delete("/api/memory/{session_id}")
def clear_memory(session_id: str):
    reset_session(session_id)
    return {"ok":True,"session_id":session_id}

@app.get("/api/evaluation/objections")
def objections():
    return objection_test_report()

@app.get("/api/evaluation/history")
def evaluation_history(limit: int = 20):
    return get_evaluation_history(limit=limit)

@app.post("/api/evaluation/score")
def evaluation_score(req: EvaluationScore):
    return score_call(req.call_id, req.scores, req.notes)

@app.websocket("/ws/voice/{session_id}")
async def voice_socket(ws: WebSocket, session_id: str):
    """Voice protocol.
    Text mode: {"type":"text","text":"..."}.
    Streaming mode: {"type":"audio_start"} -> binary 16kHz mono PCM -> {"type":"audio_stop"}.
    Server emits transcript/metrics JSON and binary Fish/ElevenLabs audio.
    {"type":"interrupt"} cancels the active response.
    """
    await ws.accept()
    audio_queue = asyncio.Queue()
    response_task = None
    stt_task = None

    async def audio_stream():
        while True:
            chunk = await audio_queue.get()
            if chunk is None:
                return
            yield chunk

    async def speak_transcript(transcript):
        nonlocal response_task
        await ws.send_json({"type":"transcript","text":transcript,"final":True})
        audio_parts = []
        async def send_audio(b):
            audio_parts.append(b)
            await ws.send_bytes(b)
        response_task = asyncio.create_task(
            run_voice_text_turn(session_id, transcript, send_audio)
        )
        try:
            result = await response_task
            await ws.send_json({"type":"response","text":result["response"]})
            if result.get("tts_error"):
                await ws.send_json({"type":"tts_error","message":result["tts_error"]})
            save_turn(
                session_id,
                transcript,
                result["response"],
                result["timings"],
                audio_bytes=b"".join(audio_parts),
            )
            await ws.send_json({
                "type":"metrics",
                "timings":result["timings"],
                "route":result["route"],
                "slots":result["memory"]["slots"],
                "objection":result.get("objection_category"),
                "escalation":result.get("escalation",False),
            })
        except asyncio.CancelledError:
            await ws.send_json({"type":"interrupted"})
            raise

    try:
        while True:
            message = await ws.receive()

            # FIX (confirmed crash, reproduced in your logs on every browser
            # close/refresh): ws.receive() is the LOW-LEVEL method - it does
            # NOT raise WebSocketDisconnect itself. Only receive_text()/
            # receive_json() do that, by calling receive() internally and
            # checking the type. This code was calling receive() directly and
            # only checking message.get("text")/.get("bytes"), neither of
            # which is set on a {"type": "websocket.disconnect"} message - so
            # the loop fell through both branches and looped back into a
            # SECOND receive() call, which Starlette rejects once the socket
            # is already in a disconnected state:
            #   RuntimeError: Cannot call "receive" once a disconnect
            #   message has been received.
            # Checking the type explicitly, first, and breaking out of the
            # loop (with the same cleanup the except WebSocketDisconnect
            # block below does) fixes this at the root instead of relying on
            # an exception handler that this code path never actually reaches.
            if message.get("type") == "websocket.disconnect":
                if response_task and not response_task.done():
                    response_task.cancel()
                if stt_task and not stt_task.done():
                    stt_task.cancel()
                break

            if message.get("text") is not None:
                data=json.loads(message["text"])
                typ=data.get("type")

                if typ=="text":
                    if response_task and not response_task.done():
                        response_task.cancel()
                    transcript=data.get("text","").strip()
                    if transcript:
                        response_task=asyncio.create_task(speak_transcript(transcript))

                elif typ=="audio_start":
                    if stt_task and not stt_task.done():
                        stt_task.cancel()
                    audio_queue=asyncio.Queue()
                    async def stt_loop():
                        async for transcript in deepgram_transcripts(audio_stream()):
                            if response_task and not response_task.done():
                                response_task.cancel()
                            await speak_transcript(transcript)
                    stt_task=asyncio.create_task(stt_loop())
                    await ws.send_json({"type":"audio_ready","provider":"deepgram"})

                elif typ=="audio_stop":
                    await audio_queue.put(None)
                    if stt_task:
                        try:
                            await stt_task
                        except Exception as exc:
                            await ws.send_json({"type":"error","message":str(exc)})

                elif typ=="interrupt":
                    if response_task and not response_task.done():
                        response_task.cancel()
                    await ws.send_json({"type":"interrupted"})

                elif typ=="reset":
                    reset_session(session_id)
                    await ws.send_json({"type":"reset_ok"})

            elif message.get("bytes") is not None:
                await audio_queue.put(message["bytes"])

    except WebSocketDisconnect:
        if response_task and not response_task.done():
            response_task.cancel()
        if stt_task and not stt_task.done():
            stt_task.cancel()


# ---------------------------------------------------------------------------
# Week 7 Day 4 — Workflows, Scheduling & Business Automation.
# Purely additive: new endpoints only. Booking/reschedule/cancel over chat
# and voice both already work through /api/chat and /ws/voice above via
# day3_agent.run_turn() -> appointment_agent.handle_appointment_turn(). The
# endpoints below are for direct API/automation use (e.g. n8n, a dashboard,
# or a QA script) and do not change anything above this line.
# ---------------------------------------------------------------------------
import appointment_store as _appt_store
import calendar_service as _calendar_service
import crm_store as _crm_store
import email_service as _email_service
from appointment_agent import _pick_employee, _within_business_hours
from day4_config import APPOINTMENT_DURATION_MINUTES as _APPT_DURATION
from day4_config import load_employees as _load_employees


class AppointmentBooking(BaseModel):
    session_id: str = "api-direct"
    channel: str = "api"
    client_name: str
    client_phone: str
    client_email: str | None = None
    property_id: str | None = None
    property_label: str | None = None
    appt_date: str  # YYYY-MM-DD
    appt_time: str  # HH:MM 24h
    employee_name: str | None = None
    notes: str = ""


class AppointmentReschedule(BaseModel):
    appointment_id: str
    appt_date: str
    appt_time: str


class AppointmentCancel(BaseModel):
    appointment_id: str


@app.get("/api/employees")
def list_employees():
    return {"employees": _load_employees()}


@app.get("/api/appointments/availability")
def appointment_availability(date: str, employee_name: str | None = None):
    """List free/booked slots for a day (and optionally a specific employee)."""
    employees = _load_employees()
    if employee_name:
        employees = [e for e in employees if e["name"].lower() == employee_name.lower()]
        if not employees:
            raise HTTPException(status_code=404, detail="Unknown employee_name")

    calendar = _calendar_service.get_calendar_provider()
    report = []
    for emp in employees:
        booked = _appt_store.list_for_employee_day(emp["name"], date)
        report.append({
            "employee": emp["name"],
            "booked_slots": [
                {"time": b["appt_time"], "duration_minutes": b["duration_minutes"], "client": b["client_name"]}
                for b in booked
            ],
        })
    return {"date": date, "calendar_provider": calendar.name, "employees": report}


@app.post("/api/appointments/book")
def api_book_appointment(req: AppointmentBooking):
    """Direct booking endpoint (bypasses the conversational flow) — e.g. for
    a staff dashboard or an n8n workflow. Applies the same business-hours
    and double-booking checks as the chat/voice flow."""
    ok, reason = _within_business_hours(req.appt_date, req.appt_time)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)

    employee = (
        {"name": req.employee_name, "email": next(
            (e["email"] for e in _load_employees() if e["name"].lower() == req.employee_name.lower()), ""
        )}
        if req.employee_name
        else _pick_employee()
    )

    calendar = _calendar_service.get_calendar_provider()
    try:
        free = calendar.is_slot_free(employee["name"], req.appt_date, req.appt_time, _APPT_DURATION)
    except _calendar_service.CalendarError as exc:
        free = None
    if free is False:
        raise HTTPException(status_code=409, detail=f"{employee['name']} is already booked at that time.")

    event = calendar.create_event(
        employee_name=employee["name"], employee_email=employee.get("email"),
        client_name=req.client_name, client_phone=req.client_phone,
        property_label=req.property_label, appt_date=req.appt_date, appt_time=req.appt_time,
        duration_minutes=_APPT_DURATION, notes=req.notes,
    )
    appt = _appt_store.create_appointment(
        session_id=req.session_id, channel=req.channel,
        client_name=req.client_name, client_phone=req.client_phone, client_email=req.client_email,
        employee_name=employee["name"], employee_email=employee.get("email"),
        property_id=req.property_id, property_label=req.property_label,
        appt_date=req.appt_date, appt_time=req.appt_time, duration_minutes=_APPT_DURATION,
        notes=req.notes, status="booked",
        calendar_event_id=event.get("event_id"), calendar_provider=event.get("provider"),
    )
    try:
        _email_service.send_employee_notification(appt)
        if req.client_email:
            _email_service.send_client_confirmation(appt)
    except _email_service.EmailError:
        pass
    return appt


@app.post("/api/appointments/reschedule")
def api_reschedule_appointment(req: AppointmentReschedule):
    target = _appt_store.get_appointment(req.appointment_id)
    if not target or target["status"] == "cancelled":
        raise HTTPException(status_code=404, detail="Appointment not found or already cancelled")

    ok, reason = _within_business_hours(req.appt_date, req.appt_time)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)

    calendar = _calendar_service.get_calendar_provider()
    try:
        free = calendar.is_slot_free(
            target["employee_name"], req.appt_date, req.appt_time,
            target["duration_minutes"], exclude_appt_id=target["id"],
        )
    except _calendar_service.CalendarError:
        free = None
    if free is False:
        raise HTTPException(status_code=409, detail=f"{target['employee_name']} is already booked at that time.")

    old_date, old_time = target["appt_date"], target["appt_time"]
    calendar.update_event(
        target.get("calendar_event_id"), employee_name=target["employee_name"],
        client_name=target["client_name"], client_phone=target["client_phone"],
        property_label=target["property_label"], appt_date=req.appt_date, appt_time=req.appt_time,
        duration_minutes=target["duration_minutes"], notes=target.get("notes", ""),
    )
    updated = _appt_store.update_appointment(req.appointment_id, appt_date=req.appt_date, appt_time=req.appt_time, status="rescheduled")
    try:
        _email_service.send_employee_reschedule_notice(updated, old_date, old_time)
    except _email_service.EmailError:
        pass
    return updated


@app.post("/api/appointments/cancel")
def api_cancel_appointment(req: AppointmentCancel):
    target = _appt_store.get_appointment(req.appointment_id)
    if not target:
        raise HTTPException(status_code=404, detail="Appointment not found")
    calendar = _calendar_service.get_calendar_provider()
    try:
        calendar.delete_event(target.get("calendar_event_id"))
    except _calendar_service.CalendarError:
        pass
    cancelled = _appt_store.cancel_appointment(req.appointment_id)
    try:
        _email_service.send_employee_cancellation_notice(cancelled)
    except _email_service.EmailError:
        pass
    return cancelled


@app.get("/api/appointments/{session_id}")
def api_list_appointments(session_id: str):
    return {"appointments": _appt_store.list_appointments(session_id=session_id)}


@app.get("/api/appointments/by-id/{appointment_id}")
def api_get_appointment(appointment_id: str):
    appt = _appt_store.get_appointment(appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return appt


# ---------------------------------------------------------------------------
# Week 7 Day 4, Task 5 — CRM: transcripts, client profiles, follow-up
# reminders. Purely additive, same as the Task 1-3 endpoints above. The
# conversational side (client history/profile, add/list reminders) already
# works over chat and voice through day3_agent.run_turn() ->
# crm_agent.handle_crm_turn(); every turn is also logged unconditionally by
# crm_agent.log_turn_to_crm(). These endpoints are for a staff dashboard,
# n8n, or QA.
# ---------------------------------------------------------------------------
class ReminderCreate(BaseModel):
    client_phone: str
    due_date: str
    note: str = ""
    session_id: str | None = None
    appointment_id: str | None = None


class ClientUpsert(BaseModel):
    phone: str
    name: str | None = None
    email: str | None = None
    preferences: dict | None = None


@app.post("/api/crm/clients/upsert")
def crm_upsert_client(req: ClientUpsert):
    """Task 4 (n8n): explicit CRM-update step an external workflow can call
    on its own, independent of the conversational booking flow."""
    client = _crm_store.upsert_client(req.phone, name=req.name, email=req.email)
    if req.preferences:
        _crm_store.merge_preferences(req.phone, req.preferences)
        client = _crm_store.get_client(req.phone)
    return client


@app.get("/api/crm/clients")
def crm_list_clients(limit: int = 100):
    return {"clients": _crm_store.list_clients(limit=limit)}


@app.get("/api/crm/clients/{phone}")
def crm_get_client_profile(phone: str):
    known_client = _crm_store.get_client(phone)
    profile = _crm_store.get_client_profile(phone)
    if not known_client and not profile["appointment_history"]:
        raise HTTPException(status_code=404, detail="No CRM record for this phone number")
    return profile


@app.get("/api/crm/transcripts/{session_id}")
def crm_get_session_transcripts(session_id: str, limit: int = 100):
    return {"transcripts": _crm_store.get_transcripts(session_id=session_id, limit=limit)}


@app.get("/api/crm/clients/{phone}/transcripts")
def crm_get_client_transcripts(phone: str, limit: int = 50):
    return {"transcripts": _crm_store.get_transcripts(phone=phone, limit=limit)}


@app.post("/api/crm/reminders")
def crm_create_reminder(req: ReminderCreate):
    _crm_store.upsert_client(req.client_phone)
    return _crm_store.create_reminder(
        client_phone=req.client_phone, session_id=req.session_id, appointment_id=req.appointment_id,
        due_date=req.due_date, note=req.note, created_by="api",
    )


@app.get("/api/crm/reminders/due")
def crm_list_due_reminders(as_of: str | None = None):
    return {"reminders": _crm_store.list_due_reminders(as_of=as_of)}


@app.get("/api/crm/reminders")
def crm_list_reminders(phone: str | None = None, status: str | None = None):
    return {"reminders": _crm_store.list_reminders(phone=phone, status=status)}


@app.post("/api/crm/reminders/{reminder_id}/complete")
def crm_complete_reminder(reminder_id: str):
    r = _crm_store.complete_reminder(reminder_id)
    if not r:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return r


@app.post("/api/crm/reminders/{reminder_id}/cancel")
def crm_cancel_reminder(reminder_id: str):
    r = _crm_store.cancel_reminder(reminder_id)
    if not r:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return r


ui_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
if os.path.exists(ui_dir):
    app.mount("/", StaticFiles(directory=ui_dir, html=True), name="ui")