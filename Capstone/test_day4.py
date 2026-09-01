"""Day 4 automated tests: calendar/email fallback providers, appointment
booking/reschedule/cancellation, and non-interference with Day 2/Day 3.

Mirrors the style of test_day3.py. Run with:
    python test_day4.py

Most tests here only need appointment_agent/appointment_store/calendar_service/
email_service (no Groq/LangGraph/Chroma required), so they can be run even
on a machine that hasn't installed the full Day 3 stack yet. The last test,
test_run_turn_integration(), imports day3_agent.run_turn like test_day3.py
does, so it needs the same full stack test_day3.py needs.
"""
import os

os.environ["DAY4_APPOINTMENT_DB"] = os.getenv("DAY4_TEST_APPOINTMENT_DB", "./day4_test_appointments.db")
os.environ["DAY4_EMAIL_LOG_FILE"] = os.getenv("DAY4_TEST_EMAIL_LOG", "./day4_test_emails.log")
os.environ["CRM_DB"] = os.getenv("DAY4_TEST_CRM_DB", "./day4_test_crm.db")
# Deterministic business hours/days for the tests below regardless of the
# real .env — Mon-Sat 10:00-19:00.
os.environ.setdefault("BUSINESS_HOURS_START", "10:00")
os.environ.setdefault("BUSINESS_HOURS_END", "19:00")
os.environ.setdefault("BUSINESS_DAYS", "0,1,2,3,4,5")
os.environ.setdefault("CALENDAR_MODE", "local")
os.environ.setdefault("EMAIL_PROVIDER", "console")

# FIX: these test databases used to persist across runs. Since the tests
# book appointments at a fixed "N business days from today" offset, running
# the suite twice on the same calendar day would re-book the SAME employee
# at the SAME slot as a leftover appointment from the previous run — a
# real, correctly-detected double-booking conflict that looks like a test
# failure but isn't a bug. Always start from a clean slate. (This only
# touches the day4_test_*.db files used by THIS test run — never the real
# appointments.db/crm.db your running server uses.)
for _test_db_file in (
    os.environ["DAY4_APPOINTMENT_DB"],
    os.environ["DAY4_EMAIL_LOG_FILE"],
    os.environ["CRM_DB"],
):
    try:
        os.remove(_test_db_file)
    except FileNotFoundError:
        pass

import appointment_agent as aa
import appointment_store as store
import calendar_service
import crm_agent
import crm_store


def _fresh_memory(agent_name="Usama Khan"):
    return {
        "slots": {},
        "last_shown_properties": [
            {
                "property_id": 1,
                "property_type": "House",
                "location": "DHA Phase 5",
                "city": "Lahore",
                "agent": agent_name,
            }
        ],
        "objections": {},
    }


def _next_weekday_iso(days_ahead_min=1):
    """Return an ISO date that is guaranteed to fall on a configured
    business day, at least `days_ahead_min` days from today."""
    from datetime import datetime, timedelta

    from day4_config import BUSINESS_DAYS

    d = datetime.now().date() + timedelta(days=days_ahead_min)
    while d.weekday() not in BUSINESS_DAYS:
        d += timedelta(days=1)
    return d.isoformat()


def test_intent_detection():
    assert aa.is_booking_intent("mujhe appointment book karni hai")
    assert aa.is_booking_intent("I'd like to schedule a site visit")
    assert aa.is_reschedule_intent("reschedule my appointment please")
    assert aa.is_reschedule_intent("waqt badalna hai")
    assert aa.is_cancel_intent("cancel appointment kardo")
    assert aa.is_cancel_intent("میٹنگ کینسل کر دیں")
    assert aa.is_cancel_intent("میری appointment cencel کر دو")
    assert aa.is_cancel_intent("cencel kar do")
    assert not aa.is_booking_intent("DHA mein kya options hain?")


def test_reschedule_intent_tolerates_real_typos():
    """Regression test for a real production bug: common Roman-Urdu/STT
    misspellings of 'reschedule' were falling through to ordinary Day 3
    chat instead of triggering the reschedule flow."""
    assert aa.is_reschedule_intent("ye appontment reshdeule krna ha mjhe")
    assert aa.is_reschedule_intent("reshedule krdo")
    assert aa.is_reschedule_intent("rescedule kar dein")
    # must NOT false-positive on unrelated words of similar length
    assert not aa.is_reschedule_intent("DHA mein residential options dikhao")
    assert not aa.is_reschedule_intent("nearby restaurant options")
    assert not aa.is_reschedule_intent("appointment book karni hai")


def test_slot_extraction_name_phone_time():
    # Regression test for the "am" substring bug (matched inside "naam").
    s = aa.extract_appointment_slots(
        "mera naam Ali Raza hai, mera number 03001234567 hai, kal shaam 5 baje aana hai"
    )
    assert s["client_name"] == "Ali Raza"
    assert s["phone"] == "+923001234567"
    assert s["time"] == "17:00"


def test_name_extraction_real_world_phrasing():
    """Regression test for a real stuck-loop bug found in production
    testing: the bot kept re-asking 'Aapka poora naam?' forever because
    none of these real user replies matched the old strict name regex."""
    assert aa._extract_name("my name is usman and mera number 0334-8829555 aur ma 14 september ko") == "Usman"
    assert aa._extract_name("naam : usman ilyas sham 4 baje") == "Usman Ilyas"
    assert aa._extract_name("pora naam:usman ilyas") == "Usman Ilyas"
    assert aa._extract_name("poora naam:m usman ilyas") == "M Usman Ilyas"
    assert aa._extract_name("krdo book") is None  # must NOT false-positive on filler/action phrases


def test_bare_name_fallback_when_no_trigger_phrase():
    """The most common real reply to 'Aapka poora naam?' is just the name
    itself with no trigger phrase at all — must be caught by the fallback,
    not left to loop forever."""
    assert aa._bare_name_fallback("usman ilyas") == "Usman Ilyas"
    assert aa._bare_name_fallback("krdo book") is None
    assert aa._bare_name_fallback("haan") is None  # a confirm reply must never be mistaken for a name
    assert aa._bare_name_fallback("03211234567") is None  # a phone number must never be mistaken for a name


def test_stuck_name_loop_resolves_end_to_end():
    """Full replay of the exact real conversation that got stuck in
    production, confirming it now resolves within the same two turns
    instead of looping on 'Aapka poora naam?' forever."""
    session = "day4-test-name-loop-regression"
    store.clear_draft(session)
    memory = {
        "slots": {"city": "Faisalabad", "property_type": "Flat"},
        "last_shown_properties": [
            {"property_id": 1, "property_type": "Flat", "location": "Canal Road", "city": "Faisalabad", "agent": "Sheikh Tanveer Ahmad"}
        ],
        "objections": {},
    }

    aa.handle_appointment_turn(session, "appointment book krdo meri", memory)
    r = aa.handle_appointment_turn(session, "my name is usman and mera number 0334-8829555 aur ma 14 september ko", memory)
    assert "naam" not in r["response"].lower() or "poora naam" in r["response"]  # only time should remain if anything
    r = aa.handle_appointment_turn(session, "naam : usman ilyas sham 4 baje", memory)
    # All base fields are now known — the agent-choice step comes next.
    assert "agent" in r["response"].lower() or "Konsa" in r["response"]
    r = aa.handle_appointment_turn(session, "1", memory)
    assert "Confirm karein" in r["response"]  # must have reached confirmation, not still asking for name
    assert "Usman Ilyas" in r["response"]
    store.clear_draft(session)


def test_spoken_digit_normalization():
    """Regression test for a real production bug found via an actual Vapi
    call: a phone number spoken as individual digit-words (native Urdu,
    Urdu-phonetic-English, or Latin) was never recognized because every
    extractor requires literal digit characters."""
    assert aa._normalize_spoken_digits("میرا نمبر زیرو تھری ٹو ون سیون سکس 9349") == "میرا نمبر 0321769349"
    assert aa._normalize_spoken_digits("میرا نمبر صفر تین دو ایک سات سات چھ نو تین چار نو ہے") == "میرا نمبر 03217769349 ہے"
    assert aa._normalize_spoken_digits("my number is zero three two one") == "my number is 0321"
    # must NOT mangle already-correct punctuated tokens (a real regression
    # caught while building this fix)
    assert aa._normalize_spoken_digits("2026-09-05 shaam 5 baje aana hai") == "2026-09-05 shaam 5 baje aana hai"
    assert aa._normalize_spoken_digits("appointment 17:00 par hai") == "appointment 17:00 par hai"

    full_number_text = "میرا نمبر زیرو تین دو ون سات سات سکس نائن تین چار نائن ہے"
    phone = aa._extract_phone(aa._normalize_spoken_digits(full_number_text))
    assert phone == "+923217769349"


def test_urdu_script_name_and_booking_intent():
    """Regression test for a real production gap found via a real Vapi
    call conducted entirely in native Urdu script: name-extraction
    triggers and booking-intent markers only covered Roman-script/English
    phrasing before this fix."""
    assert aa._extract_name("میرا نام عثمان اور میرا نمبر...") == "عثمان"
    assert aa._extract_name("میرا پورا نام محمد عثمان الیاس اور میرا نمبر...") == "محمد عثمان الیاس"
    assert aa.is_booking_intent("میری appointment بکر دو")
    assert aa.is_booking_intent("اپوائنٹمنٹ book کر دو")


def test_real_urdu_call_replay_end_to_end():
    """Full replay of a real Vapi call conducted entirely in native Urdu
    script (name, phone-as-spoken-digits, date, time), confirming the
    whole booking flow now resolves instead of endlessly re-asking."""
    session = "day4-test-real-urdu-call"
    store.clear_draft(session)
    memory = {"slots": {}, "last_shown_properties": [], "objections": {}}

    aa.handle_appointment_turn(session, "میری اپوائنٹمنٹ میری appointment book کر دو", memory)
    r = aa.handle_appointment_turn(
        session,
        "میرا نام محمد عثمان الیاس اور میرا نمبر زیرو تھری ٹو ون سات سات چھ نائن تین چار نائن ہے",
        memory,
    )
    r = aa.handle_appointment_turn(session, "15 ستمبر شام چار بجے", memory)
    assert "agent" in r["response"].lower() or "Konsa" in r["response"]
    store.clear_draft(session)


def test_booking_never_requires_phone_number():
    """Regression test for a real production bug found via a Vapi WEB test
    call: web calls have no caller ID at all (no telephony involved), and
    asking a client to speak a phone number aloud is unreliable STT-wise
    regardless of channel. Phone must never block a booking — only name,
    date, and time are required; a phone number is still captured and
    stored whenever the client does provide one."""
    session = "day4-test-no-phone-required"
    store.clear_draft(session)
    memory = {"slots": {}, "last_shown_properties": [], "objections": {}}

    aa.handle_appointment_turn(session, "appointment book karni hai", memory)
    r = aa.handle_appointment_turn(session, "mera naam Usman hai", memory)
    assert "contact number" not in r["response"].lower() and "phone" not in r["response"].lower()

    # FIX: use an offset distinct from every other test (2, 3, 4 are used
    # elsewhere) so this can never collide with another test's booking for
    # the same employee at the same date+time — a real such collision was
    # caught here during development (a correctly-detected double-booking
    # conflict between two independent tests, not a product bug).
    booking_date = _next_weekday_iso(7)
    r = aa.handle_appointment_turn(session, f"{booking_date} subah 10 baje", memory)
    assert "agent" in r["response"].lower() or "Konsa" in r["response"]

    r = aa.handle_appointment_turn(session, "koi bhi", memory)
    assert "Phone: None" not in r["response"]  # must never render a raw None

    r = aa.handle_appointment_turn(session, "haan confirm", memory)
    assert "confirm ho gayi" in r["response"]

    appts = store.list_appointments(session_id=session)
    assert appts[0]["client_phone"] is None
    assert appts[0]["status"] == "booked"
    store.clear_draft(session)


def test_time_parsing_variants():
    assert aa._extract_time("subah 10 baje") == "10:00"
    assert aa._extract_time("5pm") == "17:00"
    assert aa._extract_time("17:00") == "17:00"
    assert aa._extract_time("10:30 am") == "10:30"


def test_date_parsing_variants():
    from datetime import datetime, timedelta

    today = datetime.now().date()
    assert aa._extract_date("aaj") == today.isoformat()
    assert aa._extract_date("kal") == (today + timedelta(days=1)).isoformat()
    assert aa._extract_date("parso") == (today + timedelta(days=2)).isoformat()
    assert aa._extract_date("2026-09-15") == "2026-09-15"


def test_full_booking_flow_and_conflict():
    session = "day4-test-booking"
    store.clear_draft(session)
    memory = _fresh_memory()
    booking_date = _next_weekday_iso(2)

    r = aa.handle_appointment_turn(session, "mujhe property visit ke liye appointment chahiye", memory)
    assert r is not None and "naam" in r["response"].lower()

    r = aa.handle_appointment_turn(session, "mera naam Test Client hai", memory)
    r = aa.handle_appointment_turn(session, "03211234567", memory)
    r = aa.handle_appointment_turn(session, f"{booking_date} shaam 5 baje aana hai", memory)
    assert "agent" in r["response"].lower() or "Konsa" in r["response"]  # agent-choice step comes first

    r = aa.handle_appointment_turn(session, "Usama Khan", memory)  # pick by name
    assert "confirm" in r["response"].lower() or "Confirm" in r["response"]

    r = aa.handle_appointment_turn(session, "haan confirm", memory)
    assert "confirm ho gayi" in r["response"]

    appts = store.list_appointments(session_id=session)
    assert len(appts) == 1 and appts[0]["status"] == "booked"
    assert appts[0]["employee_name"] == "Usama Khan"  # matched from property's `agent` field

    # Second client tries to book the SAME employee at the SAME slot -> conflict.
    session2 = "day4-test-conflict"
    store.clear_draft(session2)
    memory2 = _fresh_memory()
    aa.handle_appointment_turn(session2, "appointment book karni hai", memory2)
    aa.handle_appointment_turn(session2, "mera naam Second Client hai", memory2)
    aa.handle_appointment_turn(session2, "03211112222", memory2)
    aa.handle_appointment_turn(session2, f"{booking_date} shaam 5 baje", memory2)
    r = aa.handle_appointment_turn(session2, "Usama Khan", memory2)  # pick the SAME busy employee
    assert "busy" in r["response"].lower() or "available nahi" in r["response"]


def test_reschedule_and_cancel():
    session = "day4-test-lifecycle"
    store.clear_draft(session)
    memory = _fresh_memory("Ayesha Raza")
    d1 = _next_weekday_iso(3)
    d2 = _next_weekday_iso(4)

    aa.handle_appointment_turn(session, "appointment book karni hai", memory)
    aa.handle_appointment_turn(session, "mera naam Lifecycle Client hai", memory)
    aa.handle_appointment_turn(session, "03219998888", memory)
    aa.handle_appointment_turn(session, f"{d1} subah 11 baje aana hai", memory)
    aa.handle_appointment_turn(session, "Ayesha Raza", memory)  # agent-choice step
    r = aa.handle_appointment_turn(session, "haan", memory)
    assert "confirm ho gayi" in r["response"]

    r = aa.handle_appointment_turn(session, "mujhe apni appointment reschedule karni hai", memory)
    r = aa.handle_appointment_turn(session, f"{d2} subah 11 baje kar dein", memory)
    r = aa.handle_appointment_turn(session, "haan confirm", memory)
    assert "move" in r["response"].lower()

    appt = store.find_upcoming_by_session(session)
    assert appt["appt_date"] == d2 and appt["status"] == "rescheduled"

    r = aa.handle_appointment_turn(session, "mujhe apni appointment cancel karni hai", memory)
    r = aa.handle_appointment_turn(session, "haan", memory)
    assert "cancel kar di gayi" in r["response"]

    appt = store.get_appointment(appt["id"])
    assert appt["status"] == "cancelled"


def test_business_hours_enforced():
    ok, reason = aa._within_business_hours("2020-01-01", "12:00")
    assert not ok and "guzar" in reason  # date in the past

    from datetime import datetime, timedelta

    d = datetime.now().date() + timedelta(days=1)
    from day4_config import BUSINESS_DAYS

    sunday = d
    while sunday.weekday() in BUSINESS_DAYS:
        sunday += timedelta(days=1)
    ok, reason = aa._within_business_hours(sunday.isoformat(), "12:00")
    assert not ok and "band" in reason

    ok, reason = aa._within_business_hours(_next_weekday_iso(1), "22:00")
    assert not ok and "office hours" in reason


def test_non_interference_with_day3():
    memory = {"slots": {}, "last_shown_properties": [], "objections": {}}
    ordinary_messages = [
        "DHA mein kya options hain?",
        "Budget 3 crore hai.",
        "price bohat mehnga hai",
        "Assalam o alaikum",
        "ye kitni door hai",
    ]
    for text in ordinary_messages:
        assert aa.handle_appointment_turn("day4-non-interference", text, memory) is None


def test_crm_auto_followup_on_booking():
    session = "day4-test-crm-booking"
    store.clear_draft(session)
    memory = _fresh_memory("Bilal Ahmed")
    memory["slots"] = {"city": "Lahore", "budget": 25_000_000, "property_type": "House"}
    booking_date = _next_weekday_iso(2)

    aa.handle_appointment_turn(session, "appointment book karni hai", memory)
    aa.handle_appointment_turn(session, "mera naam Sana Malik hai", memory)
    aa.handle_appointment_turn(session, "03219990001", memory)
    aa.handle_appointment_turn(session, f"{booking_date} shaam 5 baje", memory)
    aa.handle_appointment_turn(session, "Bilal Ahmed", memory)  # agent-choice step
    r = aa.handle_appointment_turn(session, "haan confirm", memory)
    assert "confirm ho gayi" in r["response"]

    phone = "+923219990001"
    client = crm_store.get_client(phone)
    assert client is not None and client["name"] == "Sana Malik"
    assert client["preferences"].get("city") == "Lahore"
    assert client["preferences"].get("budget") == 25_000_000

    reminders = crm_store.list_reminders(phone=phone, status="pending")
    assert len(reminders) == 1
    assert reminders[0]["due_date"] > booking_date  # scheduled after the visit date


def test_crm_conversational_history_and_reminders():
    memory = {"slots": {}, "last_shown_properties": [], "objections": {}}
    phone = "+923219990001"  # reuse the client created above

    r = crm_agent.handle_crm_turn("crm-view-session", f"mera profile dikhao {phone}", memory)
    assert r is not None and "Sana Malik" in r["response"]
    assert "Preferences" in r["response"]

    r = crm_agent.handle_crm_turn("crm-view-session", f"meri reminders dikhao {phone}", memory)
    assert r is not None and "Pending follow-ups" in r["response"]

    r = crm_agent.handle_crm_turn("crm-view-session", f"follow up karna hai {phone} 5 din baad payment discuss karna hai", memory)
    assert r is not None and "reminder set kar diya" in r["response"]

    all_pending = [x for x in crm_store.list_reminders(phone=phone) if x["status"] == "pending"]
    assert len(all_pending) == 2  # the auto post-visit one + this manual one


def test_crm_never_hijacks_active_booking_draft():
    session = "day4-test-crm-midflow"
    store.save_draft(session, {}, stage="collecting", intent="book")
    memory = {"slots": {}, "last_shown_properties": [], "objections": {}}
    assert crm_agent.handle_crm_turn(session, "mera profile dikhao", memory) is None
    store.clear_draft(session)


def test_crm_transcript_logging():
    session = "day4-test-crm-transcript"
    memory = {"slots": {"city": "Karachi"}, "last_shown_properties": [], "objections": {}}
    fake_result = {"response": "Karachi mein ye options hain...", "memory": memory}
    crm_agent.log_turn_to_crm(session, "Karachi mein ghar dikhao, mera number 03001112222 hai", fake_result, memory)

    transcripts = crm_store.get_transcripts(session_id=session)
    assert len(transcripts) == 2  # user + assistant
    assert transcripts[0]["role"] == "user"
    assert transcripts[0]["client_phone"] == "+923001112222"

    client = crm_store.get_client("+923001112222")
    assert client is not None and client["preferences"].get("city") == "Karachi"


def test_crm_does_not_intercept_ordinary_day3_chat():
    memory = {"slots": {}, "last_shown_properties": [], "objections": {}}
    for text in ["DHA mein kya options hain?", "Budget 3 crore hai.", "assalam o alaikum"]:
        assert crm_agent.handle_crm_turn("day4-crm-non-interference", text, memory) is None


def test_run_turn_integration():
    """Requires the full Day 3 stack (Groq/LangGraph/Chroma) — same
    requirement test_day3.py already has. Confirms the single intercept
    point in day3_agent.run_turn() routes appointment turns correctly while
    leaving ordinary turns on the existing Day 3 path."""
    from day3_agent import run_turn
    from conversation_memory import reset_session

    sid = "day4-run-turn-integration"
    reset_session(sid)

    ordinary = run_turn(sid, "Lahore mein 3 bed house dikhao")
    assert ordinary["route"] != "appointment"

    booking_date = _next_weekday_iso(2)
    r = run_turn(sid, "is property ke liye appointment book karni hai")
    assert r["route"] == "appointment"
    run_turn(sid, "mera naam Integration Test hai")
    run_turn(sid, "03001112233")
    r = run_turn(sid, f"{booking_date} shaam 4 baje")
    assert "agent" in r["response"].lower() or "Konsa" in r["response"]  # agent-choice step
    run_turn(sid, "koi bhi")  # auto-assign
    r = run_turn(sid, "haan confirm")
    assert "confirm ho gayi" in r["response"]


def test_urdu_agent_selection_variants():
    options = [
        {"name": "Usama Khan", "email": "usama@example.com", "rating": 4.8},
        {"name": "Ayesha Raza", "email": "ayesha@example.com", "rating": 4.6},
    ]

    # 1. Selection by Urdu number "نمبر دو" -> Ayesha Raza
    choice = aa._match_employee_choice("نمبر دو", options)
    assert choice == options[1]

    # 2. Selection by STT phonetic mishearing "سامہ کال" -> Usama Khan
    choice = aa._match_employee_choice("سامہ کال", options)
    assert choice == options[0]

    # 3. Selection by full Urdu script name "اسامہ خان" -> Usama Khan
    choice = aa._match_employee_choice("اسامہ خان", options)
    assert choice == options[0]

    # 4. Selection by phrase "نمبر ون کے ساتھ اپوائنٹمنٹ بک کر دو" -> Usama Khan
    choice = aa._match_employee_choice("نمبر ون کے ساتھ اپوائنٹمنٹ بک کر دو", options)
    assert choice == options[0]

    # 5. Selection by standalone digit / word "1", "2", "دوسرا", "پہلا"
    assert aa._match_employee_choice("1", options) == options[0]
    assert aa._match_employee_choice("2", options) == options[1]
    assert aa._match_employee_choice("دوسرا", options) == options[1]
    assert aa._match_employee_choice("پہلا", options) == options[0]

    # 6. Selection by Urdu script female name variants
    assert aa._match_employee_choice("عائشہ رضا", options) == options[1]
    assert aa._match_employee_choice("عائشہ رازہ", options) == options[1]

    # 7. "koi bhi" auto selection
    assert aa._match_employee_choice("koi bhi", options) == "auto"


def test_urdu_reschedule_and_availability_warning_fix():
    # 1. Intent detection tests for Urdu script reschedule and STT typos
    assert aa.is_reschedule_intent("مجھے appointment restidual کرنی ہے")
    assert aa.is_reschedule_intent("میں نے کہا ہے کہ میری appointment کو ری شیڈیول کر دو")
    assert not aa.is_booking_intent("مجھے appointment restidual کرنی ہے")
    assert not aa.is_booking_intent("میں نے کہا ہے کہ میری appointment کو ری شیڈیول کر دو")

    # 2. Replay user scenario: Book, then request reschedule in Urdu
    session = "day4-test-urdu-reschedule-fix"
    store.clear_draft(session)
    booking_date = _next_weekday_iso(2)
    memory = _fresh_memory()

    # Step 1: Book initial appointment
    aa.handle_appointment_turn(session, "appointment book kardo", memory)
    aa.handle_appointment_turn(session, "mera naam Usman hai", memory)
    aa.handle_appointment_turn(session, "03217769349", memory)
    aa.handle_appointment_turn(session, f"{booking_date} 16:00", memory)
    aa.handle_appointment_turn(session, "1", memory)
    r_confirm = aa.handle_appointment_turn(session, "haan", memory)
    assert "confirm ho gayi" in r_confirm["response"]
    assert "calendar availability" not in r_confirm["response"].lower()

    # Step 2: User requests reschedule in Urdu with typo / Urdu script
    r_resched = aa.handle_appointment_turn(session, "مجھے appointment restidual کرنی ہے", memory)
    assert "book kar dete hain" not in r_resched["response"]
    assert "Naya din aur waqt" in r_resched["response"] or "move" in r_resched["response"]

    # Step 3: Provide new date/time and confirm
    new_date = _next_weekday_iso(3)
    aa.handle_appointment_turn(session, f"{new_date} 17:00", memory)
    r_resched_done = aa.handle_appointment_turn(session, "haan", memory)
    assert "move kar di gayi hai" in r_resched_done["response"]

    store.clear_draft(session)


if __name__ == "__main__":
    test_intent_detection()
    test_reschedule_intent_tolerates_real_typos()
    test_slot_extraction_name_phone_time()
    test_name_extraction_real_world_phrasing()
    test_bare_name_fallback_when_no_trigger_phrase()
    test_stuck_name_loop_resolves_end_to_end()
    test_spoken_digit_normalization()
    test_urdu_script_name_and_booking_intent()
    test_real_urdu_call_replay_end_to_end()
    test_urdu_agent_selection_variants()
    test_urdu_reschedule_and_availability_warning_fix()
    test_booking_never_requires_phone_number()
    test_time_parsing_variants()
    test_date_parsing_variants()
    test_full_booking_flow_and_conflict()
    test_reschedule_and_cancel()
    test_business_hours_enforced()
    test_non_interference_with_day3()
    test_crm_auto_followup_on_booking()
    test_crm_conversational_history_and_reminders()
    test_crm_never_hijacks_active_booking_draft()
    test_crm_transcript_logging()
    test_crm_does_not_intercept_ordinary_day3_chat()
    print("Day 4 standalone tests passed (calendar/email fallback, booking, reschedule, cancel, non-interference, CRM logging/history/reminders).")
    try:
        test_run_turn_integration()
        print("Day 4 run_turn() integration test passed.")
    except ModuleNotFoundError as e:
        print(f"Skipped run_turn integration test — full Day 3 stack not installed here ({e}).")
    print("All Day 4 local tests passed successfully.")