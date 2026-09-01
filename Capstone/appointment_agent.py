"""Week 7 Day 4 — Task 1/2/3: Calendar + Email + Appointment management.

`handle_appointment_turn(session_id, user_text, memory)` is the single entry
point wired into day3_agent.run_turn(). It returns None when the message is
not appointment-related and no appointment flow is in progress for this
session — in that case the existing Day 3 routing runs completely
unchanged. It only returns a result dict when it should own the turn.

Works identically over text chat (/api/chat) and voice
(/ws/voice/{session_id}) because both already funnel through
day3_agent.run_turn() — see voice_pipeline.run_voice_text_turn().
"""
from __future__ import annotations

import difflib
import re
import time
from datetime import datetime, timedelta
import logging

_log = logging.getLogger("appointment_agent")

import appointment_store as store
import calendar_service
import crm_store
import email_service
from day3_objections import normalize_text
from day4_config import (
    APPOINTMENT_DURATION_MINUTES,
    BUSINESS_DAYS,
    BUSINESS_HOURS_END,
    BUSINESS_HOURS_START,
    MAX_BOOKING_HORIZON_DAYS,
    load_employees,
)
from crm_config import CANCELLATION_WINBACK_DELAY_DAYS, POST_VISIT_FOLLOWUP_DELAY_DAYS

# ---------------------------------------------------------------------------
# Intent keyword lists (English + Roman Urdu + Urdu script, matching the
# style already used in day3_router.py / day3_objections.py).
# ---------------------------------------------------------------------------
BOOKING_MARKERS = (
    "book appointment", "book a visit", "schedule a visit", "schedule appointment",
    "schedule a meeting", "schedule meeting", "meeting with", "book meeting",
    "site visit", "property visit", "meeting book", "appointment book",
    "milna chahta", "milna chahti", "visit karna", "waqt le lein", "time le lein",
    "appointment chahiye", "meeting chahiye", "dikhane ka time", "visit ka time",
    "ملاقات", "اپائنٹمنٹ", "اپوائنٹمنٹ", "ایپوائنٹمنٹ", "اپائنمنٹ",
    "میٹنگ بک", "وزٹ کرنا چاہتا", "وزٹ کرنا چاہتی", "وقت لینا",
    "ملنا چاہتا", "ملنا چاہتی", "دیکھنے کا وقت", "پراپرٹی وزٹ",
)

# FIX (found via a real Vapi call transcript, Urdu-script): real speech is
# frequently code-switched — Deepgram transcribes the English loanwords
# "book"/"appointment" in LATIN script even in an otherwise Urdu-script
# sentence ("اپوائنٹمنٹ book کر دو", "میری appointment بکر دو"). Neither
# matched any marker above (wrong Urdu spelling variant, or "book"/
# "appointment" alone isn't a listed phrase), so the whole turn fell
# through to ordinary Day 3 chat instead of starting a booking. In this
# real-estate domain, the bare words "book"/"appointment"/"booking" are
# never used for anything else, so treating them as a booking signal on
# their own is safe and high-precision.
BOOKING_LATIN_WORDS = ("book", "appointment", "booking")

RESCHEDULE_MARKERS = (
    "reschedule", "change appointment", "change my appointment", "move my appointment",
    "move my meeting", "move meeting", "change meeting",
    "time badal", "waqt badal", "date badal", "appointment change", "appointment badal",
    "دوبارہ وقت", "اپائنٹمنٹ تبدیل", "وقت تبدیل", "تاریخ تبدیل", "میٹنگ تبدیل",
    "ری شیڈیول", "ریشیڈیول", "ری شیڈول", "ریشیڈول", "ری شیڈیولing", "ریشیڈولنگ", "ری شیڈولنگ", "تبدیل", "بدل",
    "reschedual", "restidual", "reshedul", "reshdule", "re-schedule", "re schedule",
)

CANCEL_MARKERS = (
    "cancel appointment", "cancel my appointment", "cancel the meeting", "cancel booking",
    "appointment cancel", "meeting cancel", "cancel kardo", "cancel kar dein",
    "appointment khatam", "nahi aana", "cancel karna hai", "mansookh", "mansookh karni", "meeting mansookh",
    "اپائنٹمنٹ کینسل", "میٹنگ کینسل", "بکنگ کینسل", "منسوخ", "کینسل کرنا ہے",
    "کینسل", "کنسل", "منسوخ", "کینسلشن", "کینسلنگ", "منسوخ کرنا",
    "cencel", "cancle", "cancal", "cincel", "cancel",
)


def is_cancel_intent(text):
    s = _norm(text)
    if any(m in s for m in CANCEL_MARKERS):
        return True
    return _fuzzy_word_match(s, "cancel", cutoff=0.75, min_len=5)

AVAILABILITY_QUESTION_MARKERS = (
    "are you free", "is agent free", "koi slot available", "kya time available",
    "kab free hain", "available ho", "kya waqt milega",
    "کیا فری ہیں", "کیا وقت دستیاب ہے", "کب فری ہیں",
)

CONFIRM_MARKERS = (
    "yes", "haan", "ji haan", "ji han", "confirm", "confirmed", "theek hai", "ok", "okay",
    "sahi hai", "book kar dein", "book kardo", "kar dein", "kar do", "kardo", "kar do confirm",
    "cancel kar do", "cancel kardo", "cancel kar dein", "کینسل کر دو", "منسوخ کر دو",
    "move kar do", "move kardo", "move kar dein", "change kar do",
    "ہاں", "جی ہاں", "ٹھیک ہے", "کنفرم", "بک کر دیں", "بک کر دو", "کینسل کر دیں", "تبدیل کر دیں",
)



DECLINE_MARKERS = (
    "no", "nahi", "nahi chahiye", "not now", "not this", "wrong",
    "نہیں", "غلط",
)

WEEKDAYS = {
    # canonical -> python weekday (Mon=0)
    **{d: i for i, d in enumerate(
        ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    )},
    "peer": 0, "pir": 0, "somwar": 0, "پیر": 0,
    "mangal": 1, "منگل": 1,
    "budh": 2, "بدھ": 2,
    "jumeraat": 3, "jumerat": 3, "جمعرات": 3,
    "juma": 4, "jumma": 4, "جمعہ": 4,
    "hafta": 5, "saneechar": 5, "sanichar": 5, "ہفتہ": 5,
    "itwar": 6, "اتوار": 6,
}

MONTHS = {
    "jan": 1, "january": 1, "جنوری": 1,
    "feb": 2, "february": 2, "فروری": 2,
    "mar": 3, "march": 3, "مارچ": 3,
    "apr": 4, "april": 4, "اپریل": 4,
    "may": 5, "مئی": 5,
    "jun": 6, "june": 6, "جون": 6,
    "jul": 7, "july": 7, "جولائی": 7,
    "aug": 8, "august": 8, "اگست": 8,
    "sep": 9, "sept": 9, "september": 9, "ستمبر": 9,
    "oct": 10, "october": 10, "اکتوبر": 10,
    "nov": 11, "november": 11, "نومبر": 11,
    "dec": 12, "december": 12, "دسمبر": 12,
}

PHONE_PATTERN = re.compile(r"(?:\+?92|0)?[\s\-]?3\d{2}[\s\-]?\d{7}")

# Words that must stop a name capture partway through ("usman AND mera
# number...") or that mean a short bare reply isn't a name at all
# ("krdo book"). Deliberately includes connector words, phone/contact
# words, date/time words (including common misspellings like "sham" for
# "shaam"), and pure filler/action phrases.
NAME_STOPWORDS = {
    "and", "aur", "mera", "meri", "mero", "number", "no", "contact", "phone", "mobile",
    "hai", "hoon", "hun", "se", "ko", "ka", "ki", "ke", "tareekh", "date", "din",
    "baje", "waqt", "time", "sham", "shaam", "subah", "dopher", "dopeher", "raat",
    "morning", "evening", "afternoon", "night", "am", "pm", "naam", "poora", "pura",
    "pora", "full", "name", "krdo", "kardo", "kar", "do", "kro", "ker", "book",
    "ji", "please", "abhi", "jaldi", "theek", "thik", "ok", "okay", "done", "hoga",
    # FIX (found via a real Vapi call transcript, native Urdu script): all
    # of the above were Roman-script only. Real Deepgram output for spoken
    # Urdu is very often native Urdu script, not romanized — added the
    # equivalent stopwords so the same collision-avoidance applies there.
    "ہے", "ہوں", "سے", "کو", "کا", "کی", "کے", "تاریخ", "دن", "بجے", "وقت",
    "صبح", "شام", "دوپہر", "رات", "نام", "پورا", "مکمل", "نمبر", "میرا", "میری",
    "کر", "کریں", "کریں،", "دیں", "بک", "جی", "براہ", "مہربانی", "ابھی", "جلدی", "ٹھیک",
    "اور", "پر", "میں", "لیے", "بھی", "تو", "ہوں،", "گا", "گی", "گے", "چاہوں", "چاہتا", "چاہتی",
}


# ---------------------------------------------------------------------------
# Spoken-digit normalization — see _normalize_spoken_digits() below.
# ---------------------------------------------------------------------------
_URDU_NATIVE_DIGIT_WORDS = {
    "صفر": "0", "زیرو": "0", "ایک": "1", "دو": "2", "تین": "3", "چار": "4",
    "پانچ": "5", "چھ": "6", "چھے": "6", "سات": "7", "آٹھ": "8", "نو": "9",
}

_URDU_PHONETIC_ENGLISH_DIGIT_WORDS = {
    "زیرو": "0", "ون": "1", "ٹو": "2", "تھری": "3", "فور": "4",
    "فائیو": "5", "سکس": "6", "سیون": "7", "ایٹ": "8", "نائن": "9",
}

_LATIN_ENGLISH_DIGIT_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
}

_ALL_DIGIT_WORDS = {**_URDU_NATIVE_DIGIT_WORDS, **_URDU_PHONETIC_ENGLISH_DIGIT_WORDS, **_LATIN_ENGLISH_DIGIT_WORDS}


def _normalize_spoken_digits(text):
    """Convert spelled-out digit words into a contiguous digit run so
    phone/time regexes (which need literal digit characters) can find
    them. FIX (found via a real Vapi call transcript): a client speaking
    their phone number gets transcribed by Deepgram as individual spoken
    digit-words — either native Urdu ("زیرو تھری ٹو") or English words
    phonetically rendered in Urdu script ("زیرو تھری ٹو" = "zero three
    two") or plain Latin ("zero three two") — none of which matched any
    extraction regex before, since those require actual digit characters.
    Consecutive digit-words are joined with no separator (e.g. "زیرو
    تھری" -> "03"); anything else passes through unchanged.

    Known limitation: this only covers single digit-words (0-9), not
    multi-digit Urdu ordinals used for dates ("پندرہ" = fifteen) — dates
    already work fine via literal digits ("15 ستمبر"), so this wasn't
    extended to that much larger vocabulary.
    """
    words = text.split()
    out_parts = []
    buffer = ""
    for w in words:
        # FIX: only strip leading/trailing punctuation, never internal —
        # stripping ALL non-word characters (my first attempt) mangled
        # already-correct tokens like "2026-09-05" into "20260905" and
        # "17:00" into "1700", breaking date/time patterns that require
        # those separators. A word containing internal punctuation is
        # never a bare digit-word, so it's left completely untouched.
        stripped = w.strip(".,!?؟،۔:")
        digit = _ALL_DIGIT_WORDS.get(stripped) or _ALL_DIGIT_WORDS.get(stripped.lower())
        if digit is None and stripped.isdigit():
            digit = stripped
        if digit is not None:
            buffer += digit
        else:
            if buffer:
                out_parts.append(buffer)
                buffer = ""
            out_parts.append(w)
    if buffer:
        out_parts.append(buffer)
    return " ".join(out_parts)


def _norm(text):
    return normalize_text(text)


def is_booking_intent(text):
    s = _norm(text)
    if is_reschedule_intent(text) or is_cancel_intent(text):
        return False
    if any(m in s for m in BOOKING_MARKERS):
        return True
    if any(re.search(rf"\b{w}\b", s) for w in BOOKING_LATIN_WORDS):
        return True
    # Fuzzy-match Urdu-script spelling variants of "appointment" that
    # aren't in BOOKING_MARKERS verbatim — Urdu transliteration of English
    # loanwords isn't standardized, and STT output varies.
    for word in re.findall(r"[\u0600-\u06FF]+", text):
        if len(word) >= 6 and difflib.SequenceMatcher(None, word, "اپائنٹمنٹ").ratio() >= 0.75:
            return True
    return False


def is_reschedule_intent(text):
    s = _norm(text)
    if any(m in s for m in RESCHEDULE_MARKERS):
        return True
    for word in re.findall(r"[a-z]+", text.lower()):
        if word == "schedule":
            continue
        if len(word) >= 6 and difflib.SequenceMatcher(None, word, "reschedule").ratio() >= 0.75:
            return True
    return False


def _fuzzy_word_match(text, target, cutoff=0.8, min_len=6):
    for word in re.findall(r"[a-z]+", text.lower()):
        if len(word) < min_len:
            continue
        if difflib.SequenceMatcher(None, word, target).ratio() >= cutoff:
            return True
    return False



def is_availability_question(text):
    return any(m in _norm(text) for m in AVAILABILITY_QUESTION_MARKERS)


def _is_confirm(text):
    s = _norm(text)
    return any(m in s for m in CONFIRM_MARKERS) and not any(m in s for m in DECLINE_MARKERS)


def _is_decline(text):
    s = _norm(text)
    return any(m in s for m in DECLINE_MARKERS)


# ---------------------------------------------------------------------------
# Slot extraction — date, time, phone, name, notes
# ---------------------------------------------------------------------------
def _extract_phone(text):
    m = PHONE_PATTERN.search(text.replace(" ", "").replace("-", ""))
    if not m:
        m = PHONE_PATTERN.search(text)
    if not m:
        return None
    digits = re.sub(r"\D", "", m.group(0))
    if digits.startswith("92"):
        digits = digits[2:]
    digits = digits.lstrip("0")
    return "+92" + digits if digits else None


def _extract_name(text):
    # FIX (found via real transcript testing): the old regex required the
    # name to be immediately followed by "hai"/end-of-string/comma/period,
    # which breaks the moment a real sentence continues past the name
    # ("my name is usman AND mera number..."). Rewritten as: find a trigger
    # phrase, then greedily collect consecutive name-like words until
    # hitting a stopword (a connector, a phone/date/time word, punctuation,
    # or a digit) or the 4-word cap — no specific ending token required.
    triggers = ["mera naam", "my name is", "poora naam", "pura naam", "pora naam",
                "full name", "naam hai", "naam",
                # FIX (found via a real Vapi call transcript): all triggers
                # above are Roman-script only. Real spoken Urdu is very
                # often transcribed in native Urdu script, which matched
                # none of them. Longer/more specific phrases listed first
                # so they win over the bare "نام" match.
                "میرا پورا نام", "میرا نام", "پورا نام", "نام ہے", "نام"]
    lowered = text.lower()
    for trig in triggers:
        idx = lowered.find(trig)
        if idx == -1:
            continue
        after = text[idx + len(trig):].lstrip(" :-\u2013\u2014")
        words = after.split()
        collected = []
        for w in words:
            wl = re.sub(r"[.,!?]+$", "", w.lower())
            if wl in NAME_STOPWORDS or not re.match(r"^[A-Za-z\u0600-\u06FF]+$", w):
                break
            collected.append(w)
            if len(collected) >= 4:
                break
        if collected:
            return " ".join(collected).title()
    return None


def _bare_name_fallback(text):
    """When the bot's last question specifically asked for the client's
    name and the reply has no trigger phrase and no other extractable
    signal (no phone/date/time, not a confirm/decline), assume the whole
    message IS the name — the single most common real reply to "Aapka
    poora naam?" is just the name itself, with nothing else attached."""
    if _is_confirm(text) or _is_decline(text):
        return None
    words = re.findall(r"[A-Za-z\u0600-\u06FF]+", text)
    if not words or len(words) > 5:
        return None
    cleaned = [w for w in words if w.lower() not in NAME_STOPWORDS]
    if not cleaned:
        return None
    return " ".join(cleaned[:4]).title()


def _extract_date(text):
    s = _norm(text)
    today = datetime.now().date()

    if any(w in s for w in ("aaj", "today", "آج")):
        return today.isoformat()
    if any(w in s for w in ("parso", "پرسوں", "day after tomorrow")):
        return (today + timedelta(days=2)).isoformat()
    if any(w in s for w in ("kal", "tomorrow", "کل")):
        return (today + timedelta(days=1)).isoformat()

    # ISO date already, e.g. 2026-09-05
    m = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", s)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        try:
            return datetime(y, mo, d).date().isoformat()
        except ValueError:
            pass

    # DD/MM or DD-MM(-YYYY)
    m = re.search(r"\b(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{2,4}))?\b", s)
    if m:
        d, mo, y = m.groups()
        d, mo = int(d), int(mo)
        y = int(y) if y else today.year
        if y < 100:
            y += 2000
        try:
            candidate = datetime(y, mo, d).date()
            if not y and candidate < today:
                candidate = candidate.replace(year=candidate.year + 1)
            return candidate.isoformat()
        except ValueError:
            pass

    # "15 september" / "september 15" / with Urdu month names
    month_pat = "|".join(sorted(MONTHS.keys(), key=len, reverse=True))
    m = re.search(rf"\b(\d{{1,2}})\s+({month_pat})\b", s) or re.search(
        rf"\b({month_pat})\s+(\d{{1,2}})\b", s
    )
    if m:
        groups = m.groups()
        if groups[0].isdigit():
            day, month_word = int(groups[0]), groups[1]
        else:
            month_word, day = groups[0], int(groups[1])
        mo = MONTHS[month_word]
        year = today.year
        try:
            candidate = datetime(year, mo, day).date()
            if candidate < today:
                candidate = candidate.replace(year=year + 1)
            return candidate.isoformat()
        except ValueError:
            pass

    # weekday name -> next occurrence
    for word, wd in WEEKDAYS.items():
        if word in s:
            delta = (wd - today.weekday()) % 7
            delta = delta or 7  # "monday" said on Monday means next Monday
            return (today + timedelta(days=delta)).isoformat()

    return None


def _extract_time(text):
    s = _norm(text)

    # 24h or explicit HH:MM (optionally am/pm)
    m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\s*(am|pm|صبح|شام)?\b", s)
    if m:
        h, mnt, ap = int(m.group(1)), int(m.group(2)), m.group(3)
        h = _apply_ampm(h, ap, s)
        return f"{h:02d}:{mnt:02d}"

    # "5pm", "5 pm", "5 baje", "5 baje shaam"
    m = re.search(r"\b(\d{1,2})\s*(am|pm)\b", s)
    if m:
        h, ap = int(m.group(1)), m.group(2)
        h = _apply_ampm(h, ap, s)
        return f"{h:02d}:00"

    m = re.search(r"\b(\d{1,2})\s*(?:baje|بجے)\b", s)
    if m:
        h = int(m.group(1))
        h = _apply_ampm(h, None, s)
        return f"{h:02d}:00"

    return None


def _has_word(context, word):
    """Word-boundary containment check.

    FIX (confirmed bug): a plain `word in context` substring check falsely
    matched "am" inside ordinary words like "naam" (name) or "kaam" (work),
    and "pm" inside e.g. "aapm...". Short 2-letter EN markers collide with
    common Roman-Urdu words constantly, so every marker below is matched on
    a word boundary instead of as a bare substring.
    """
    return re.search(rf"(?<![^\W_]){re.escape(word)}(?![^\W_])", context, flags=re.UNICODE) is not None


def _apply_ampm(hour, ap, context):
    morning_markers = ("subah", "morning", "صبح", "am")
    evening_markers = ("shaam", "evening", "dopeher", "dopher", "afternoon", "raat", "night", "شام", "pm")
    if ap == "am" or any(_has_word(context, w) for w in morning_markers):
        return hour % 12
    if ap == "pm" or any(_has_word(context, w) for w in evening_markers):
        return (hour % 12) + 12
    # No explicit marker: business hours are 10:00-19:00, so a bare small
    # number ("5 baje", "3 baje") almost always means afternoon/evening for
    # a property-viewing context. This is a heuristic, not a certainty —
    # extend from real transcripts if a genuine "5 AM" request ever occurs.
    if 1 <= hour <= 7:
        return hour + 12
    return hour


def _extract_notes(text):
    m = re.search(
        r"(?:requirement|requirements|note|notes|zarurat|zaroorat)[:\-]?\s*(.+)$",
        text, flags=re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    return None


def extract_appointment_slots(text):
    # FIX (found via a real Vapi call transcript): apply spoken-digit
    # normalization once, up front, so phone/time extraction can see
    # spelled-out digit words as actual digits. Safe to run for date/name
    # too — it only ever changes recognized digit-words, leaving
    # everything else (including names) untouched.
    normalized = _normalize_spoken_digits(text)
    slots = {}
    date = _extract_date(normalized)
    time_ = _extract_time(normalized)
    phone = _extract_phone(normalized)
    name = _extract_name(text)
    notes = _extract_notes(text)
    if date:
        slots["date"] = date
    if time_:
        slots["time"] = time_
    if phone:
        slots["phone"] = phone
    if name:
        slots["client_name"] = name
    if notes:
        slots["notes"] = notes
    return slots


# ---------------------------------------------------------------------------
# Employee assignment & availability
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Employee assignment & availability
# ---------------------------------------------------------------------------
EMPLOYEE_NAME_ALIASES = {
    "usama khan": [
        "usama", "osama", "khan", "usama khan", "osama khan",
        "اسامہ", "سامہ", "وسامہ", "اسامہ خان", "سامہ خان", "وسامہ خان",
        "سامہ کال", "سامه", "اسامه", "ساما", "اساما"
    ],
    "ayesha raza": [
        "ayesha", "aisha", "raza", "rajah", "ayesha raza", "aisha raza",
        "عائشہ", "ایشہ", "عایشہ", "رضا", "رازہ", "راجا", "عائشہ رضا", "عائشہ رازہ"
    ],
    "bilal ahmed": [
        "bilal", "ahmed", "ahmad", "bilal ahmed", "bilal ahmad",
        "بلال", "احمد", "بلال احمد"
    ],
    "front desk": [
        "front", "desk", "front desk",
        "فرنٹ", "ڈیسک", "فرنٹ ڈیسک"
    ]
}


def _match_single_employee_name(query, employee_dict_or_name):
    if not query:
        return False

    name_str = employee_dict_or_name["name"] if isinstance(employee_dict_or_name, dict) else str(employee_dict_or_name)
    name_clean = name_str.strip().lower()
    query_raw = query.strip()
    query_clean = query_raw.lower()

    # 1. Known Aliases (Urdu script, Roman Urdu, STT variants)
    aliases = EMPLOYEE_NAME_ALIASES.get(name_clean, [])
    for alias in aliases:
        if alias in query_clean or alias in query_raw:
            return True

    # 2. English first name or full name matching
    first_name = name_clean.split()[0]
    if first_name in query_clean or name_clean in query_clean:
        return True

    # 3. Individual token matches (length >= 3)
    query_tokens = [w for w in re.split(r"\s+", query_clean) if len(w) >= 3]
    name_tokens = [w for w in re.split(r"\s+", name_clean) if len(w) >= 3]
    for n_tok in name_tokens:
        if n_tok in query_tokens:
            return True

    # 4. Fuzzy ratio check
    for target in aliases + [name_clean, first_name]:
        if len(target) >= 4 and difflib.SequenceMatcher(None, target, query_clean).ratio() >= 0.75:
            return True

    return False


def _pick_employee(preferred_name=None, property_agent=None):
    employees = load_employees()
    if preferred_name:
        for e in employees:
            if _match_single_employee_name(preferred_name, e):
                return e
    if property_agent:
        for e in employees:
            if _match_single_employee_name(property_agent, e):
                return e
    # Round-robin by current appointment count so load is spread out.
    counts = {e["name"]: 0 for e in employees}
    for appt in store.list_appointments(limit=200):
        if appt["employee_name"] in counts and appt["status"] in ("booked", "rescheduled"):
            counts[appt["employee_name"]] += 1
    return min(employees, key=lambda e: counts.get(e["name"], 0))


# ---------------------------------------------------------------------------
# Agent selection — let the client see and choose who they get, instead of
# always silently auto-assigning.
# ---------------------------------------------------------------------------
def _suggest_employees(property_agent=None, n=2):
    """Up to `n` employees to offer the client: the property's own listed
    agent first (if we have a matching employee record), then the
    highest-rated remaining staff, so the choice is short and relevant
    rather than dumping the entire directory on the client."""
    employees = load_employees()
    if not employees:
        return []
    chosen = []
    if property_agent:
        for e in employees:
            if _match_single_employee_name(property_agent, e):
                chosen.append(e)
                break
    remaining = [e for e in employees if e not in chosen]
    remaining.sort(key=lambda e: e.get("rating", 0), reverse=True)
    for e in remaining:
        if len(chosen) >= n:
            break
        chosen.append(e)
    return chosen[:n]


def _format_employee_options_message(options, retry=False):
    if not options:
        return "Ji, filhaal koi agent available nahi hai — humari team aapko jald contact karegi."
    lines = []
    for i, e in enumerate(options, start=1):
        rating = e.get("rating")
        rating_str = f" ({rating}★)" if rating else ""
        lines.append(f"{i}. {e['name']}{rating_str}")
    prefix = "Maaf kijiye, samajh nahi aaya. " if retry else ""
    return (
        prefix + "Konsa agent aapko pasand hoga? " + "; ".join(lines)
        + ". (Number ya naam bata dein, ya 'koi bhi' kahein.)"
    )


ANY_EMPLOYEE_MARKERS = ("koi bhi", "kisi ko", "aap hi bata", "any", "whoever", "jo bhi", "کوئی بھی")

EMPLOYEE_ORDINAL_WORDS = {
    # Index 0 (Option 1)
    "1": 0, "۱": 0, "one": 0, "pehla": 0, "pehli": 0, "pehle": 0, "پہلا": 0, "پہلی": 0, "پہلے": 0, "first": 0, "1st": 0, "ایک": 0, "ون": 0, "یک": 0,
    # Index 1 (Option 2)
    "2": 1, "۲": 1, "two": 1, "dusra": 1, "dusri": 1, "dusre": 1, "doosra": 1, "doosri": 1, "doosre": 1, "دوسرا": 1, "دوسری": 1, "دوسرے": 1, "second": 1, "2nd": 1, "دو": 1, "ٹو": 1,
    # Index 2 (Option 3)
    "3": 2, "۳": 2, "three": 2, "teesra": 2, "teesri": 2, "teesre": 2, "تیسرا": 2, "تیسری": 2, "تیسرے": 2, "third": 2, "3rd": 2, "تین": 2, "تھری": 2,
    # Index 3 (Option 4)
    "4": 3, "۴": 3, "four": 3, "chautha": 3, "chauthi": 3, "chauthe": 3, "چوتھا": 3, "چوتھی": 3, "چوتھے": 3, "fourth": 3, "4th": 3, "چار": 3, "فور": 3,
}


def _match_employee_choice(text, options):
    """Returns a matched employee dict, the sentinel string "auto" (client
    said 'koi bhi'/'any'), or None if the reply didn't match any option."""
    if not options:
        return None

    s = _norm(text)
    if any(m in s for m in ANY_EMPLOYEE_MARKERS):
        return "auto"

    normalized = _normalize_spoken_digits(text)

    # 1. Explicit option patterns like "number 1", "number 2", "نمبر 1", "نمبر 2", "نمبر دو", "نمبر ون"
    m_opt = re.search(r"(?:number|no\.?|num|option|نمبر)\s*([1-9]|۱|۲|۳|۴|ایک|دو|تین|چار|ون|ٹو|تھری|فور)", text, re.IGNORECASE)
    if m_opt:
        token = m_opt.group(1).lower()
        if token in EMPLOYEE_ORDINAL_WORDS:
            idx = EMPLOYEE_ORDINAL_WORDS[token]
            if idx < len(options):
                return options[idx]

    m_opt_norm = re.search(r"(?:number|no\.?|num|option|نمبر)\s*([1-9])", normalized, re.IGNORECASE)
    if m_opt_norm:
        idx = int(m_opt_norm.group(1)) - 1
        if 0 <= idx < len(options):
            return options[idx]

    # 2. Check employee names (English, Roman Urdu, Urdu script, STT variants)
    for e in options:
        if _match_single_employee_name(text, e):
            return e

    # 3. Ordinal word / digit match across text (find earliest occurrence in string if multiple match)
    earliest_match = None
    earliest_pos = float("inf")

    for word, idx in EMPLOYEE_ORDINAL_WORDS.items():
        if idx >= len(options):
            continue
        if re.match(r"^[a-zA-Z0-9]+$", word):
            pattern = rf"\b{re.escape(word)}\b"
        else:
            pattern = re.escape(word)

        for match_str in (text, s, normalized):
            m = re.search(pattern, match_str, re.IGNORECASE)
            if m and m.start() < earliest_pos:
                earliest_pos = m.start()
                earliest_match = options[idx]

    if earliest_match:
        return earliest_match

    return None


def _within_business_hours(appt_date, appt_time):
    try:
        d = datetime.strptime(appt_date, "%Y-%m-%d").date()
        t = datetime.strptime(appt_time, "%H:%M").time()
    except ValueError:
        return False, "Date/time samajh nahi aaya. Format: 2026-09-05 aur waqt 15:00."
    if d.weekday() not in BUSINESS_DAYS:
        return False, "Ji, us din office band hota hai. Koi aur din bata dein."
    if d < datetime.now().date():
        return False, "Ji, ye tareekh guzar chuki hai. Aage ki tareekh bata dein."
    if (d - datetime.now().date()).days > MAX_BOOKING_HORIZON_DAYS:
        return False, f"Ji, hum sirf agle {MAX_BOOKING_HORIZON_DAYS} din tak booking le sakte hain."
    start = datetime.strptime(BUSINESS_HOURS_START, "%H:%M").time()
    end = datetime.strptime(BUSINESS_HOURS_END, "%H:%M").time()
    if not (start <= t < end):
        return False, f"Ji, hamare office hours {BUSINESS_HOURS_START} se {BUSINESS_HOURS_END} tak hain. Koi waqt isi range mein bata dein."
    return True, None


def _property_label_from_memory(memory):
    shown = (memory or {}).get("last_shown_properties") or []
    if not shown:
        slots = (memory or {}).get("slots") or {}
        parts = [slots.get("property_type"), slots.get("location"), slots.get("city")]
        parts = [p for p in parts if p]
        return (None, None, " ".join(parts) if parts else None)
    row = shown[0]
    property_id = row.get("property_id")
    agent = row.get("agent")
    label_parts = [row.get("property_type"), row.get("location") or row.get("unit_type"), row.get("city")]
    label = ", ".join(p for p in label_parts if p) or "Selected property"
    return (property_id, agent, label)


REQUIRED_BOOKING_FIELDS = ("client_name", "date", "time")

# Phone is intentionally NOT required (real testing showed asking for it
# verbally on a call is unreliable — see _normalize_spoken_digits for why —
# and Vapi web-test calls have no caller ID to auto-fill it with anyway).
# It's still captured and stored whenever the client states it naturally
# or a channel supplies known_phone; it just never blocks the booking.


def _missing_fields(slots):
    return [f for f in REQUIRED_BOOKING_FIELDS if not slots.get(f)]


def _ask_for(fields):
    prompts = {
        "client_name": "Aapka poora naam?",
        "date": "Kis din aana chahenge (e.g. kal, ya 15 September)?",
        "time": "Kis waqt (e.g. shaam 5 baje)?",
    }
    return " ".join(prompts[f] for f in fields)


def _result(response, memory, timings, listings=None):
    return {
        "response": response,
        "listings": listings or [],
        "route": "appointment",
        "memory": memory,
        "objection_category": None,
        "escalation": False,
        "timings": timings,
    }


# ---------------------------------------------------------------------------
# Flow implementations
# ---------------------------------------------------------------------------
def _start_booking_draft(session_id, memory, extra_slots, known_phone=None):
    property_id, agent, label = _property_label_from_memory(memory)
    slots = {"property_id": property_id, "property_label": label, "property_agent": agent}
    # FIX (requested after real Vapi call testing): on a real phone call,
    # asking the client to speak their phone number digit-by-digit is
    # error-prone for STT. When the calling channel already knows the
    # caller's number (Vapi's own caller-ID metadata), pre-fill it here so
    # the client is never even asked — a number they explicitly type/say
    # in the conversation still overrides this via the extraction merge
    # below, so this never blocks someone booking on behalf of someone else.
    if known_phone:
        slots["phone"] = _extract_phone(known_phone) or known_phone
    slots.update(extra_slots)
    store.save_draft(session_id, slots, stage="collecting", intent="book")
    return slots


def _handle_booking(session_id, text, memory, channel, known_phone=None):
    draft = store.get_draft(session_id)
    extracted = extract_appointment_slots(text)

    if not draft or draft.get("intent") != "book":
        slots = _start_booking_draft(session_id, memory, extracted, known_phone=known_phone)
    else:
        slots = dict(draft.get("slots") or {})
        slots.update({k: v for k, v in extracted.items() if v})

    stage = (draft or {}).get("stage", "collecting") if draft.get("intent") == "book" else "collecting"

    # Confirmation stage: user is answering "confirm karein?"
    if stage == "confirming":
        if _is_confirm(text):
            return _finalize_booking(session_id, slots, memory, channel)
        if _is_decline(text):
            store.save_draft(session_id, slots, stage="collecting", intent="book")
            return "Ji koi masla nahi. Kya tareekh ya waqt tabdeel karna chahenge?"
        # Not a clear yes/no — treat as more info and re-ask confirmation below.

    # Agent-choice stage: user is answering "konsa agent pasand hoga?"
    if stage == "choosing_employee":
        options = slots.get("_employee_options") or []
        choice = _match_employee_choice(text, options)
        if choice is None:
            store.save_draft(session_id, slots, stage="choosing_employee", intent="book")
            return _format_employee_options_message(options, retry=True)
        employee = _pick_employee(property_agent=slots.get("property_agent")) if choice == "auto" else choice
        slots["employee_name"] = employee["name"]
        slots["employee_email"] = employee.get("email")
        slots.pop("_employee_options", None)
        # falls through to the availability check + confirmation below

    # FIX (found via real transcript testing): the single most common real
    # reply to "Aapka poora naam?" is just the bare name with no trigger
    # phrase at all ("usman ilyas"). If nothing else was extracted this
    # turn and the name is still missing, treat the whole message as the
    # name instead of asking the same question forever.
    if not slots.get("client_name") and not extracted and stage not in ("confirming", "choosing_employee"):
        candidate = _bare_name_fallback(text)
        if candidate:
            slots["client_name"] = candidate

    missing = _missing_fields(slots)
    if missing:
        store.save_draft(session_id, slots, stage="collecting", intent="book")
        if not slots.get("property_label"):
            return "Ji bilkul, appointment book kar dete hain. Sabse pehle: kaunsi property ke liye visit chahiye? " + _ask_for(missing)
        return "Ji bilkul, appointment book kar dete hain. " + _ask_for(missing)

    # Ask which agent the client wants BEFORE checking availability/
    # confirming, instead of always silently auto-assigning one.
    if not slots.get("employee_name"):
        options = _suggest_employees(property_agent=slots.get("property_agent"))
        if len(options) <= 1:
            chosen = options[0] if options else _pick_employee(property_agent=slots.get("property_agent"))
            slots["employee_name"] = chosen["name"]
            slots["employee_email"] = chosen.get("email")
        else:
            slots["_employee_options"] = options
            store.save_draft(session_id, slots, stage="choosing_employee", intent="book")
            return _format_employee_options_message(options)

    ok, reason = _within_business_hours(slots["date"], slots["time"])
    if not ok:
        store.save_draft(session_id, slots, stage="collecting", intent="book")
        return reason

    employee = {"name": slots["employee_name"], "email": slots.get("employee_email")}
    calendar = calendar_service.get_calendar_provider()
    try:
        free = calendar.is_slot_free(employee["name"], slots["date"], slots["time"], APPOINTMENT_DURATION_MINUTES)
    except Exception as exc:
        # FIX: this failure used to be swallowed with zero visibility,
        # making it impossible to diagnose *why* Google Calendar rejected
        # the check (permissions, wrong calendar ID, API not enabled...).
        # Now it's logged to the server console so the real Google error
        # text is visible on the very next attempt. Broadened from
        # "except CalendarError" to "except Exception" since a real crash
        # elsewhere in this file proved a plain TypeError can also occur —
        # a calendar hiccup of any kind must never block/crash a booking.
        _log.warning("Calendar availability check failed (%s): %s", calendar.name, exc)
        free = None  # unknown — ask user to confirm anyway, note it in the message

    store.save_draft(session_id, slots, stage="confirming", intent="book")

    if free is False:
        next_slot = _next_available_slot(employee["name"], slots["date"], slots["time"])
        store.save_draft(session_id, slots, stage="collecting", intent="book")
        if next_slot:
            return (
                f"Ji, {slots['date']} {slots['time']} par {employee['name']} pehle se busy hain. "
                f"Agla available slot {next_slot[0]} {next_slot[1]} hai — ye theek hai? "
                "Ya koi aur din/waqt bata dein."
            )
        return f"Ji, {slots['date']} {slots['time']} par {employee['name']} available nahi hain. Koi aur din/waqt bata dein."

    availability_note = ""
    phone_line = f", Phone: {slots['phone']}" if slots.get("phone") else ""
    return (
        f"Ji, {slots['date']} ko {slots['time']} baje, {slots.get('property_label') or 'property'} ke liye "
        f"{employee['name']} ke sath appointment set kar sakte hain{availability_note}. "
        f"Client: {slots.get('client_name')}{phone_line}. "
        "Confirm karein — aap is waqt free hain? (haan/nahi)"
    )


def _next_available_slot(employee_name, appt_date, appt_time):
    """Very small linear search over the same day, then the next business day."""
    calendar = calendar_service.get_calendar_provider()
    d = datetime.strptime(appt_date, "%Y-%m-%d").date()
    start = datetime.strptime(BUSINESS_HOURS_START, "%H:%M").time()
    end = datetime.strptime(BUSINESS_HOURS_END, "%H:%M").time()
    for day_offset in range(0, 2):
        day = d + timedelta(days=day_offset)
        if day.weekday() not in BUSINESS_DAYS:
            continue
        t = datetime.combine(day, start)
        end_dt = datetime.combine(day, end)
        while t < end_dt:
            candidate_time = t.strftime("%H:%M")
            try:
                if calendar.is_slot_free(employee_name, day.isoformat(), candidate_time, APPOINTMENT_DURATION_MINUTES):
                    return day.isoformat(), candidate_time
            except Exception:
                break
            t += timedelta(minutes=APPOINTMENT_DURATION_MINUTES)
    return None


def _finalize_booking(session_id, slots, memory, channel):
    calendar = calendar_service.get_calendar_provider()
    # FIX (found via real testing): a Google Calendar failure here used to
    # crash the whole request with a 500, even though the identical failure
    # mode in is_slot_free() above degrades gracefully. Our own appointments
    # table is the source of truth regardless of calendar sync — a calendar
    # hiccup should never block a confirmed booking.
    try:
        event = calendar.create_event(
            employee_name=slots.get("employee_name"),
            employee_email=slots.get("employee_email"),
            client_name=slots.get("client_name"),
            client_phone=slots.get("phone"),
            property_label=slots.get("property_label"),
            appt_date=slots["date"],
            appt_time=slots["time"],
            duration_minutes=APPOINTMENT_DURATION_MINUTES,
            notes=slots.get("notes", ""),
        )
    except Exception as exc:
        # Broadened from "except CalendarError" — a real crash elsewhere in
        # this file proved a plain TypeError can also occur here; any
        # calendar failure, of any kind, must degrade gracefully.
        _log.warning("Calendar create_event failed (%s): %s", calendar.name, exc)
        event = {"event_id": None, "provider": f"{calendar.name}-sync-failed"}
        try:
            crm_store.create_reminder(
                client_phone=None, session_id=session_id, appointment_id=None,
                due_date=datetime.now().date().isoformat(),
                note=(
                    f"URGENT: Google Calendar sync failed while booking {slots.get('client_name')} "
                    f"({slots.get('phone') or 'no phone on file'}) for {slots['date']} {slots['time']} — add to calendar manually. "
                    f"Error: {exc}"
                ),
                created_by="system",
            )
        except Exception:
            pass
    client_email = slots.get("client_email")
    if not client_email and slots.get("phone"):
        try:
            client_rec = crm_store.get_client(slots["phone"])
            if client_rec:
                client_email = client_rec.get("email")
        except Exception:
            pass

    emp_email = slots.get("employee_email")
    if not emp_email and slots.get("employee_name"):
        import day4_config as d4cfg
        for emp in d4cfg.load_employees():
            if _match_single_employee_name(slots["employee_name"], emp):
                emp_email = emp.get("email")
                break


    appt = store.create_appointment(
        session_id=session_id,
        channel=channel,
        client_name=slots.get("client_name"),
        client_phone=slots.get("phone"),
        client_email=client_email,
        employee_name=slots.get("employee_name"),
        employee_email=emp_email,
        property_id=slots.get("property_id"),
        property_label=slots.get("property_label"),
        appt_date=slots["date"],
        appt_time=slots["time"],
        duration_minutes=APPOINTMENT_DURATION_MINUTES,
        notes=slots.get("notes", ""),
        status="booked",
        calendar_event_id=event.get("event_id"),
        calendar_provider=event.get("provider"),
    )
    try:
        email_service.send_employee_notification(appt)
    except Exception as exc:
        _log.warning("send_employee_notification failed: %s", exc)

    try:
        if appt.get("client_email"):
            email_service.send_client_confirmation(appt)
    except Exception as exc:
        _log.warning("send_client_confirmation failed: %s", exc)

    # Task 5 CRM: identify the client, save their preferences, and schedule
    # an automatic post-visit follow-up. Wrapped defensively so a CRM
    # hiccup can never block a successful booking.
    try:
        phone = slots.get("phone")
        if phone:
            crm_store.upsert_client(phone, name=slots.get("client_name"))
            crm_store.link_session(session_id, phone)
            crm_store.merge_preferences(phone, (memory or {}).get("slots") or {})
            followup_due = (
                datetime.strptime(slots["date"], "%Y-%m-%d") + timedelta(days=POST_VISIT_FOLLOWUP_DELAY_DAYS)
            ).date().isoformat()
            crm_store.create_reminder(
                client_phone=phone, session_id=session_id, appointment_id=appt["id"],
                due_date=followup_due,
                note=f"Follow up with {slots.get('client_name')} after their {slots.get('property_label') or 'property'} viewing with {slots.get('employee_name')}.",
                created_by="system",
            )
    except Exception:
        pass

    store.clear_draft(session_id)
    return (
        f"Ji, appointment confirm ho gayi hai (ID: {appt['id']}). "
        f"{slots['date']} ko {slots['time']} baje {slots.get('employee_name')} aapse "
        f"{slots.get('property_label') or 'property'} ke silsile mein milenge. "
        "Employee ko email bhi bhej di gayi hai."
    )


def _handle_reschedule(session_id, text, memory):
    draft = store.get_draft(session_id)
    extracted = extract_appointment_slots(text)

    if not draft or draft.get("intent") != "reschedule":
        target = store.find_upcoming_by_session(session_id)
        if not target and extracted.get("phone"):
            matches = store.find_upcoming_by_phone(extracted["phone"])
            target = matches[0] if matches else None
        if not target:
            session_phone = crm_store.get_phone_for_session(session_id)
            if session_phone:
                matches = store.find_upcoming_by_phone(session_phone)
                target = matches[0] if matches else None
        if not target:
            return "Ji, mujhe aapki koi active appointment nahi mili. Aapka registered phone number bata dein taake main dhoond sakoon."
        slots = dict(extracted)
        store.save_draft(session_id, slots, stage="collecting", intent="reschedule", target_appointment_id=target["id"])
        draft = store.get_draft(session_id)
    else:
        slots = dict(draft.get("slots") or {})
        slots.update({k: v for k, v in extracted.items() if v})
        store.save_draft(session_id, slots, stage=draft.get("stage", "collecting"), intent="reschedule", target_appointment_id=draft.get("target_appointment_id"))

    target_id = draft.get("target_appointment_id")
    target = store.get_appointment(target_id) if target_id else None
    if not target:
        store.clear_draft(session_id)
        return "Ji, ye appointment ab system mein nahi mili. Nayi booking karna chahenge?"

    if draft.get("stage") == "confirming":
        if _is_confirm(text):
            ok, reason = _within_business_hours(slots["date"], slots["time"])
            if not ok:
                return reason
            calendar = calendar_service.get_calendar_provider()
            try:
                free = calendar.is_slot_free(
                    target["employee_name"], slots["date"], slots["time"],
                    target["duration_minutes"], exclude_appt_id=target["id"],
                )
            except Exception as exc:
                _log.warning("Calendar availability check failed during reschedule (%s): %s", calendar.name, exc)
                free = None
            if free is False:
                return f"Ji, {slots['date']} {slots['time']} par {target['employee_name']} available nahi hain. Koi aur waqt bata dein."
            old_date, old_time = target["appt_date"], target["appt_time"]
            # FIX (same class of bug as _finalize_booking): a Google
            # Calendar failure here must not crash the reschedule — the
            # appointments table is still updated regardless of sync status.
            try:
                calendar.update_event(
                    target.get("calendar_event_id"),
                    employee_name=target["employee_name"], employee_email=target.get("employee_email"),
                    client_name=target["client_name"],
                    client_phone=target["client_phone"], property_label=target["property_label"],
                    appt_date=slots["date"], appt_time=slots["time"],
                    duration_minutes=target["duration_minutes"], notes=target.get("notes", ""),
                )
            except Exception as exc:
                # FIX: was previously "except calendar_service.CalendarError"
                # only — but a real production crash showed this can also
                # raise a plain TypeError (e.g. a missing keyword argument),
                # which slipped straight past that guard and crashed the
                # whole request with a 500. Broadened to catch ANY calendar
                # failure, of any kind, so this can never happen again — the
                # appointments table is still the source of truth regardless.
                _log.warning("Calendar update_event failed during reschedule (%s): %s", calendar.name, exc)
                try:
                    crm_store.create_reminder(
                        client_phone=target.get("client_phone"), session_id=session_id, appointment_id=target["id"],
                        due_date=datetime.now().date().isoformat(),
                        note=f"URGENT: Google Calendar sync failed while rescheduling appointment {target['id']} — update calendar manually. Error: {exc}",
                        created_by="system",
                    )
                except Exception:
                    pass
            updated = store.update_appointment(target["id"], appt_date=slots["date"], appt_time=slots["time"], status="rescheduled")
            try:
                email_service.send_employee_reschedule_notice(updated, old_date, old_time)
                if updated and updated.get("client_email"):
                    email_service.send_client_confirmation(updated)
            except Exception as exc:
                _log.warning("send_employee_reschedule_notice failed: %s", exc)

            try:
                phone = target.get("client_phone")
                if phone:
                    crm_store.upsert_client(phone, name=target.get("client_name"))
                    crm_store.link_session(session_id, phone)
                    crm_store.merge_preferences(phone, (memory or {}).get("slots") or {})
            except Exception:
                pass
            store.clear_draft(session_id)
            return f"Ji, appointment {old_date} {old_time} se {slots['date']} {slots['time']} par move kar di gayi hai. Employee ko inform kar diya gaya hai."
        if _is_decline(text):
            store.save_draft(session_id, slots, stage="collecting", intent="reschedule", target_appointment_id=target_id)
            return "Theek hai, naya din/waqt bata dein."

    if not (slots.get("date") and slots.get("time")):
        store.save_draft(session_id, slots, stage="collecting", intent="reschedule", target_appointment_id=target_id)
        return (
            f"Ji, aapki appointment abhi {target['appt_date']} {target['appt_time']} par hai "
            f"({target.get('property_label') or 'property'} ke liye). Naya din aur waqt bata dein."
        )

    store.save_draft(session_id, slots, stage="confirming", intent="reschedule", target_appointment_id=target_id)
    return f"Ji, {slots['date']} ko {slots['time']} baje move karna confirm karein? (haan/nahi)"


def _handle_cancel(session_id, text, memory):
    draft = store.get_draft(session_id)
    extracted = extract_appointment_slots(text)

    if not draft or draft.get("intent") != "cancel":
        target = store.find_upcoming_by_session(session_id)
        if not target and extracted.get("phone"):
            matches = store.find_upcoming_by_phone(extracted["phone"])
            target = matches[0] if matches else None
        if not target:
            session_phone = crm_store.get_phone_for_session(session_id)
            if session_phone:
                matches = store.find_upcoming_by_phone(session_phone)
                target = matches[0] if matches else None
        if not target:
            return "Ji, mujhe aapki koi active appointment nahi mili. Registered phone number bata dein."
        store.save_draft(session_id, {}, stage="confirming", intent="cancel", target_appointment_id=target["id"])
        target_id = target["id"]
    else:
        target_id = draft.get("target_appointment_id")

    target = store.get_appointment(target_id) if target_id else None
    if not target:
        store.clear_draft(session_id)
        return "Ji, ye appointment nahi mili."

    stage = (draft or {}).get("stage")
    if stage == "confirming":

        if _is_confirm(text):
            calendar = calendar_service.get_calendar_provider()
            try:
                calendar.delete_event(target.get("calendar_event_id"))
            except Exception as exc:
                _log.warning("Calendar delete_event failed during cancel (%s): %s", calendar.name, exc)
            cancelled = store.cancel_appointment(target["id"])
            try:
                email_service.send_employee_cancellation_notice(cancelled)
            except Exception as exc:
                _log.warning("send_employee_cancellation_notice failed: %s", exc)

            # Task 5 CRM: log the cancellation against the client and offer
            # a later win-back follow-up, defensively — never blocks the
            # cancellation itself.
            try:
                phone = target.get("client_phone")
                if phone:
                    crm_store.upsert_client(phone, name=target.get("client_name"))
                    crm_store.link_session(session_id, phone)
                    winback_due = (datetime.now() + timedelta(days=CANCELLATION_WINBACK_DELAY_DAYS)).date().isoformat()
                    crm_store.create_reminder(
                        client_phone=phone, session_id=session_id, appointment_id=target["id"],
                        due_date=winback_due,
                        note=f"Check back in with {target.get('client_name')} after their cancelled {target.get('property_label') or 'property'} viewing.",
                        created_by="system",
                    )
            except Exception:
                pass
            store.clear_draft(session_id)
            return f"Ji, {target['appt_date']} {target['appt_time']} ki appointment cancel kar di gayi hai. Employee ko bhi inform kar diya gaya hai."
        if _is_decline(text):
            store.clear_draft(session_id)
            return "Theek hai, appointment cancel nahi ki gayi."

    return (
        f"Ji, aapki appointment {target['appt_date']} {target['appt_time']} par "
        f"({target.get('property_label') or 'property'}) hai. Cancel karna confirm karein? (haan/nahi)"
    )


def _channel_from_memory(memory):
    # There is nothing voice-specific to see here; app_day3.py can pass the
    # right channel explicitly via handle_appointment_turn's caller if ever
    # needed. Default to "chat" — harmless either way since it is only used
    # for reporting.
    return "chat"


def has_active_draft(session_id: str) -> bool:
    """Task 5 wiring helper: lets crm_agent (and run_turn) know a
    booking/reschedule/cancel conversation already owns this session, so
    CRM commands ("client history dikhao", "reminder add karo") don't
    hijack a turn mid-flow."""
    return bool(store.get_draft(session_id))


def handle_appointment_turn(session_id, user_text, memory, known_phone=None):
    """Return a run_turn()-shaped result dict, or None to defer to Day 3.

    known_phone: optional caller-ID style phone number supplied by the
    calling channel (e.g. Vapi's own call metadata on a real phone call).
    Pre-fills the phone slot so the client is never asked to speak digits
    aloud — purely additive, defaults to None everywhere else (chat/tests
    are completely unaffected).
    """
    started = time.perf_counter()
    draft = store.get_draft(session_id)
    in_progress = bool(draft)

    if is_cancel_intent(user_text):
        response = _handle_cancel(session_id, user_text, memory)
    elif is_reschedule_intent(user_text):
        response = _handle_reschedule(session_id, user_text, memory)
    elif in_progress and draft.get("intent") == "cancel":
        response = _handle_cancel(session_id, user_text, memory)
    elif in_progress and draft.get("intent") == "reschedule":
        response = _handle_reschedule(session_id, user_text, memory)
    elif in_progress and draft.get("intent") == "book":
        response = _handle_booking(session_id, user_text, memory, _channel_from_memory(memory), known_phone=known_phone)
    elif is_booking_intent(user_text) or is_availability_question(user_text):
        response = _handle_booking(session_id, user_text, memory, _channel_from_memory(memory), known_phone=known_phone)
    else:
        return None

    timings = {"appointment_ms": (time.perf_counter() - started) * 1000}
    timings["total_ms"] = timings["appointment_ms"]
    return _result(response, memory, timings)