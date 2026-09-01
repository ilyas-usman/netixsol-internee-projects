"""Persistent conversation memory: turns + structured real-estate slots."""
from __future__ import annotations
import json, os, re, sqlite3, threading
from typing import Any

from day3_config import MEMORY_DB

_LOCK = threading.Lock()

def _conn():
    os.makedirs(os.path.dirname(os.path.abspath(MEMORY_DB)), exist_ok=True)
    c = sqlite3.connect(MEMORY_DB, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c

def init_memory():
    with _LOCK:
        c = _conn()
        c.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            session_id TEXT PRIMARY KEY,
            slots_json TEXT NOT NULL DEFAULT '{}',
            last_shown_json TEXT NOT NULL DEFAULT '[]',
            objection_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            text TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id, id);
        """)
        c.commit(); c.close()

def _ensure(session_id):
    c = _conn()
    c.execute("INSERT OR IGNORE INTO conversations(session_id) VALUES (?)", (session_id,))
    c.commit(); c.close()

def get_state(session_id: str) -> dict[str, Any]:
    _ensure(session_id)
    c = _conn()
    row = c.execute("SELECT * FROM conversations WHERE session_id=?", (session_id,)).fetchone()
    turns = c.execute(
        "SELECT role,text,metadata_json,created_at FROM turns WHERE session_id=? ORDER BY id DESC LIMIT ?",
        (session_id, 12),
    ).fetchall()
    c.close()
    return {
        "session_id": session_id,
        "slots": json.loads(row["slots_json"] or "{}"),
        "last_shown_properties": json.loads(row["last_shown_json"] or "[]"),
        "objections": json.loads(row["objection_json"] or "{}"),
        "history": [dict(x) | {"metadata": json.loads(x["metadata_json"] or "{}")} for x in reversed(turns)],
    }

def update_state(session_id, *, slots=None, last_shown_properties=None, objections=None):
    _ensure(session_id)
    c = _conn()
    current = c.execute("SELECT * FROM conversations WHERE session_id=?", (session_id,)).fetchone()
    payload = {
        "slots_json": json.dumps(slots if slots is not None else json.loads(current["slots_json"] or "{}"), ensure_ascii=False),
        "last_shown_json": json.dumps(last_shown_properties if last_shown_properties is not None else json.loads(current["last_shown_json"] or "[]"), ensure_ascii=False),
        "objection_json": json.dumps(objections if objections is not None else json.loads(current["objection_json"] or "{}"), ensure_ascii=False),
    }
    c.execute("""UPDATE conversations SET slots_json=?,last_shown_json=?,objection_json=?,
                 updated_at=CURRENT_TIMESTAMP WHERE session_id=?""",
              (payload["slots_json"], payload["last_shown_json"], payload["objection_json"], session_id))
    c.commit(); c.close()

def add_turn(session_id, role, text, metadata=None):
    _ensure(session_id)
    c = _conn()
    c.execute("INSERT INTO turns(session_id,role,text,metadata_json) VALUES (?,?,?,?)",
              (session_id, role, text, json.dumps(metadata or {}, ensure_ascii=False)))
    c.commit(); c.close()

def reset_session(session_id):
    c = _conn()
    c.execute("DELETE FROM turns WHERE session_id=?", (session_id,))
    c.execute("DELETE FROM conversations WHERE session_id=?", (session_id,))
    c.commit(); c.close()

# --------------------------------------------------------------------------
# FIX: Deepgram (STT, "multi" language mode) frequently transcribes spoken
# code-switched Urdu-English into pure Urdu Unicode script, including
# phonetic Urdu-script renderings of ENGLISH number words ("eight" -> "ایٹ")
# as well as actual Urdu number words ("aath" -> "آٹھ"). The original
# parse_money() only matched a literal ASCII digit immediately before a
# unit word ("3 crore" -> 30000000) - it silently returned None for BOTH
# of the above, because neither contains an ASCII digit at all. This was
# confirmed directly: re.search(...) on "ایٹ کروڑ" and "آٹھ کروڑ" both
# returned None under the original regex.
#
# NUMBER_WORDS below covers 1-20 in both forms (native Urdu numerals and
# common phonetic Urdu-script transliterations of English number words),
# so parse_money can resolve "budget آٹھ کروڑ" or "budget ایٹ کروڑ" the
# same way it already resolves "budget 8 crore" or "budget 3 crore".
# This does NOT fully solve STT-garbling on its own (a badly mistranscribed
# number word still can't be recovered), but it removes the specific,
# confirmed gap where a CORRECTLY transcribed spelled-out number word was
# being silently dropped regardless of STT quality.
# --------------------------------------------------------------------------
NUMBER_WORDS = {
    # Native Urdu number words
    "aik": 1, "ek": 1, "ایک": 1,
    "do": 2, "دو": 2,
    "teen": 3, "تین": 3,
    "char": 4, "چار": 4,
    "paanch": 5, "panch": 5, "پانچ": 5,
    "chay": 6, "chhay": 6, "چھ": 6,
    "saat": 7, "سات": 7,
    "aath": 8, "آٹھ": 8,
    "nau": 9, "نو": 9,
    "das": 10, "دس": 10,
    "gyarah": 11, "گیارہ": 11,
    "barah": 12, "بارہ": 12,
    "terah": 13, "تیرہ": 13,
    "chaudah": 14, "چودہ": 14,
    "pandrah": 15, "پندرہ": 15,
    "solah": 16, "سولہ": 16,
    "satrah": 17, "سترہ": 17,
    "atharah": 18, "اٹھارہ": 18,
    "unnees": 19, "انیس": 19,
    "bees": 20, "بیس": 20,
    # Common phonetic Urdu-script renderings of ENGLISH number words -
    # this is the specific gap that caused the "budget ایٹ کروڑ" miss.
    # Transliteration varies by speaker/STT model; these cover the most
    # common renderings. Extend this list from real call transcripts as
    # new spellings show up - it can never be fully exhaustive.
    "one": 1, "ون": 1,
    "two": 2, "ٹو": 2,
    "three": 3, "تھری": 3,
    "four": 4, "فور": 4,
    "five": 5, "فائیو": 5,
    "six": 6, "سکس": 6,
    "seven": 7, "سیون": 7,
    "eight": 8, "ایٹ": 8, "ایٹھ": 8,
    "nine": 9, "نائن": 9,
    "ten": 10, "ٹین": 10,
}

MONEY_UNIT_WORDS = {
    "crore": 10_000_000, "cr": 10_000_000, "karor": 10_000_000, "کروڑ": 10_000_000,
    "lac": 100_000, "lakh": 100_000, "لاکھ": 100_000, "لاک": 100_000,
    "million": 1_000_000, "m": 1_000_000,
}

_UNIT_PATTERN = "|".join(re.escape(u) for u in MONEY_UNIT_WORDS)
_NUMBER_WORD_PATTERN = "|".join(re.escape(w) for w in sorted(NUMBER_WORDS, key=len, reverse=True))


def parse_money(text: str):
    """Convert common Pakistani money phrases to PKR - digits OR spelled-out
    number words (Urdu or common English-word transliterations), in either
    Urdu or Latin script, followed by a crore/lakh/million unit word."""
    s = text.lower().replace(",", "").strip()

    # Digit form: "3 crore", "8 lakh" (original behavior, unchanged)
    m = re.search(rf"(\d+(?:\.\d+)?)\s*({_UNIT_PATTERN})\b", s)
    if m:
        n = float(m.group(1))
        unit = m.group(2)
        return int(n * MONEY_UNIT_WORDS[unit])

    # Spelled-out word form: "aath crore", "آٹھ کروڑ", "ایٹ کروڑ"
    m = re.search(rf"({_NUMBER_WORD_PATTERN})\s*({_UNIT_PATTERN})\b", s)
    if m:
        n = NUMBER_WORDS[m.group(1)]
        unit = m.group(2)
        return int(n * MONEY_UNIT_WORDS[unit])

    return None

def heuristic_slots(text: str) -> dict:
    """Cheap deterministic slot extraction used when Groq is unavailable or incomplete."""
    s = text.lower()
    out = {}

    money = parse_money(s)
    if money:
        out["budget"] = money

    # FIX: every "v in s" check below was a plain substring test, which
    # silently matches inside unrelated words — most damagingly, "room"
    # inside the ordinary English word "bedrooms". A user saying "kya
    # bedrooms hain?" about a flat they were just shown had their
    # correct property_type ("Flat") overwritten with "Room" every
    # single time, with no visible error — this is very likely the
    # "sometimes I say flat but it shows me a house/room" symptom.
    # \b anchors each variant to real word edges instead.
    def _word_in(variant, text_):
        return re.search(rf"\b{re.escape(variant)}\b", text_) is not None

    # FIX: city/location/purpose/property_type lists were English-only,
    # so they matched nothing at all against pure Urdu-script STT output
    # (confirmed: zero matches on real transcript text). Added Urdu-script
    # equivalents alongside each English entry. Extend from real call
    # transcripts as new spellings/cities show up.
    cities = [
        ("Lahore", ["lahore", "لاہور"]),
        ("Karachi", ["karachi", "کراچی"]),
        ("Islamabad", ["islamabad", "اسلام آباد", "اسلام اباد"]),
        ("Rawalpindi", ["rawalpindi", "راولپنڈی"]),
        ("Faisalabad", ["faisalabad", "فیصل آباد"]),
        ("Multan", ["multan", "ملتان"]),
        ("Gujranwala", ["gujranwala", "گوجرانوالہ"]),
        ("Peshawar", ["peshawar", "پشاور"]),
        ("Gwadar", ["gwadar", "گوادر"]),
    ]
    for canonical, variants in cities:
        if any(_word_in(v, s) for v in variants):
            out["city"] = canonical

    locations = [
        ("DHA Defence", ["dha defence", "ڈی ایچ اے ڈیفنس"]),
        ("DHA Phase 1", ["dha phase 1", "ڈی ایچ اے فیز 1"]),
        ("DHA Phase 2", ["dha phase 2", "ڈی ایچ اے فیز 2"]),
        ("DHA Phase 3", ["dha phase 3", "ڈی ایچ اے فیز 3"]),
        ("DHA Phase 4", ["dha phase 4", "ڈی ایچ اے فیز 4"]),
        ("DHA Phase 5", ["dha phase 5", "ڈی ایچ اے فیز 5"]),
        ("DHA Phase 6", ["dha phase 6", "ڈی ایچ اے فیز 6"]),
        ("DHA Phase 7", ["dha phase 7", "ڈی ایچ اے فیز 7"]),
        ("DHA Phase 8", ["dha phase 8", "ڈی ایچ اے فیز 8"]),
        ("DHA", ["dha", "ڈی ایچ اے", "ڈی ایچ ای"]),
        ("Bahria Town", ["bahria town", "بحریہ ٹاؤن"]),
        ("Bahria", ["bahria", "بحریہ"]),
        ("Gulberg", ["gulberg", "گلبرگ"]),
        ("Johar Town", ["johar town", "جوہر ٹاؤن"]),
        ("Allama Iqbal Town", ["allama iqbal town", "علامہ اقبال ٹاؤن"]),
        ("Model Town", ["model town", "ماڈل ٹاؤن"]),
    ]
    for canonical, variants in sorted(locations, key=lambda x: max(len(v) for v in x[1]), reverse=True):
        if any(_word_in(v, s) for v in variants):
            out["location"] = canonical
            break

    if any(_word_in(t, s) for t in ["for sale", "buy", "purchase", "kharid", "خریدنا", "بائے", "سیل"]):
        out["purpose"] = "For Sale"
    elif any(_word_in(t, s) for t in ["rent", "rental", "kiraye", "کرایہ", "کرائے"]):
        out["purpose"] = "For Rent"

    m = re.search(r"\b([1-9]|10)\s*(?:bed|bedroom|bedrooms)\b", s)
    if m:
        out["bedrooms"] = int(m.group(1))

    property_types = [
        ("House", ["house", "ghar", "گھر", "ہاؤس"]),
        ("Flat", ["flat", "فلیٹ"]),
        ("Apartment", ["apartment", "اپارٹمنٹ"]),
        ("Plot", ["plot", "پلاٹ"]),
        ("Farm House", ["farm house", "فارم ہاؤس"]),
        ("Room", ["room", "کمرہ"]),
    ]
    for canonical, variants in property_types:
        if any(_word_in(v, s) for v in variants):
            out["property_type"] = canonical
            break

    return out

init_memory()