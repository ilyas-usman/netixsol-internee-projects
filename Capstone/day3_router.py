"""Day 3 intent router + slot extraction. SQL vs RAG vs both vs chat."""
from __future__ import annotations
import json, re
from groq import Groq
from day3_config import GROQ_MODEL, GROQ_FALLBACK_MODEL
from conversation_memory import heuristic_slots

ROUTER_SYSTEM = """You are a routing/extraction component for a Pakistani real-estate voice agent.
Return JSON only with:
route: one of sql, rag, both, chat
slots: object containing only explicitly stated or clearly corrected values among:
budget (PKR integer), city, location, bedrooms (integer), purpose, property_type, investment_goal (boolean)
comparison: one of none, cheaper, more_expensive, similar
objection: one of none, price, trust, location, investment, builder, maintenance
reason: short string.
Resolve corrections such as 'nahi, 2 crore hi' using the current message.
Do not invent values. A question about exact listings/prices/bedrooms/availability is sql.
A question about FAQs, payment plans, developer/builder information is rag.
A recommendation mixing exact listings with a knowledge question is both.
Small talk is chat."""

# FIX (confirmed bug, not a guess - tested directly against real transcript
# text): every one of these lists was English/Roman-script only. Deepgram's
# "multi" mode frequently transcribes spoken Urdu-English into pure Urdu
# Unicode script, which none of the original `"word" in text` checks could
# ever match - "lahore" in "لاہور" is structurally false regardless of
# .lower(). That silently forced route="chat" with zero heuristic slots on
# any Urdu-script turn, leaving the live LLM call as the ONLY thing standing
# between a correct extraction and a completely missed one. Added Urdu-script
# equivalents alongside each English entry below. This can never be fully
# exhaustive - extend it from real call transcripts as new phrasings appear.
sql_words=[
    "price","property","house","flat","plot","shop","office","warehouse","plaza",
    "commercial","school","hospital","nearby","amenities","amenity","bed","bedroom",
    "available","option","location","dha","bahria","lahore","karachi","islamabad","faisalabad",
    # Urdu-script equivalents
    "پرائس","قیمت","پراپرٹی","گھر","ہاؤس","فلیٹ","پلاٹ","شاپ","دکان","آفس","دفتر",
    "ویئر ہاؤس","پلازہ","کمرشل","سکول","اسکول","ہسپتال","ہاسپٹل","قریب","نزدیک","امینیٹیز","سہولیات","یوٹیلٹیز","یوٹیلیٹی",
    "بیڈ","بیڈروم","دستیاب","آپشن","لوکیشن","ڈی ایچ اے","بحریہ","لاہور","کراچی","اسلام آباد","فیصل آباد",
]
rag_words=[
    "payment plan","installment","down payment","refund","booking","developer","builder",
    "reputation","policy",
    # Urdu-script equivalents
    "پیمنٹ پلان","قسط","ڈاؤن پیمنٹ","ریفنڈ","بکنگ","ڈویلپر","بلڈر","ساکھ","پالیسی",
]
from day3_objections import detect_objection, normalize_text

FAREWELL_MARKERS = (
    "allah hafiz", "allah hafez", "khuda hafiz", "allahhafiz", "khudahafiz",
    "bye", "goodbye", "ok bye", "okay bye", "bye bye", "exit", "see you",
    # Urdu-script variations
    "الافیس", "الافس", "الله حافظ", "اللہ حافظ", "خدا حافظ", "بائے", "باے",
    "بائے بائے", "اوکے اللہ حافظ", "او کے اللہ حافظ", "اللہ حافط", "الله حافط",
    "اللہ فیس", "الله فیس", "اللہ پاک حافظ", "الله پاک حافظ",
)

casual_markers = (
    "hi", "hello", "hey", "salam", "assalam o alaikum",
    "assalamualaikum", "thanks", "thank you", "good morning",
    "good evening", "kya haal", "kya hal", "kya chal",
    "aur sunao", "or sunao", "how are you", "how is life",
    "what are you doing", "kya kr rhe", "kya kar rahe",
    "pagal ho kya", "pagal hu kya",
    # Farewell markers
    *FAREWELL_MARKERS,
    # Urdu-script equivalents
    "السلام علیکم", "وعلیکم السلام", "سلام", "شکریہ", "کیا حال ہے", "کیا حال ہیں",
    "کیا چل رہا ہے", "کیسے ہیں", "کیا کر رہے ہیں",
)
property_markers = (
    "budget", "crore", "lakh", "lac", "house", "ghar", "flat",
    "plot", "shop", "office", "warehouse", "property", "option",
    "dha", "bahria", "lahore", "karachi", "islamabad", "faisalabad",
    # Urdu-script equivalents
    "بجٹ", "کروڑ", "لاکھ", "گھر", "فلیٹ", "پلاٹ", "شاپ", "دکان", "آفس",
    "پراپرٹی", "آپشن", "ڈی ایچ اے", "بحریہ", "لاہور", "کراچی", "اسلام آباد", "فیصل آباد",
)

def _heuristic_route(text):
    s = normalize_text(text)
    slots = heuristic_slots(text)

    # Farewell override in heuristic: if input is a farewell and not a property request, force route='chat'
    if any(marker in s for marker in FAREWELL_MARKERS) and not any(marker in s for marker in property_markers):
        return {"route": "chat", "slots": {}, "comparison": "none", "objection": "none", "reason": "farewell override"}

    comparison = "none"
    if any(x in s for x in ["sasti","cheaper","kam price","kam mehngi","under that","us se sasti",
                             "سستی","سستا","کم قیمت","اس سے سستی"]): comparison="cheaper"
    if any(x in s for x in ["mehngi","expensive","higher budget","مہنگی","مہنگا"]): comparison="more_expensive"

    objection = detect_objection(text)

    sql = any(x in s for x in sql_words); rag = any(x in s for x in rag_words)
    route = "both" if sql and rag else "sql" if sql else "rag" if rag else "chat"
    if comparison != "none" or objection == "price":
        route = "sql"
    elif slots and route == "chat":
        route = "sql"
    return {"route":route,"slots":slots,"comparison":comparison,"objection":objection,"reason":"heuristic fallback"}

def route_and_extract(text, state=None):
    """
    Route the message and extract slots.

    LLM extraction is used first, but deterministic heuristic extraction
    is merged afterward so obvious entities such as DHA and 3 crore
    cannot be silently lost.
    """
    state = state or {}

    normalized = normalize_text(text)

    # Farewell override: if input is a goodbye/farewell and not a property request, force route='chat'
    if any(marker in normalized for marker in FAREWELL_MARKERS) and not any(marker in normalized for marker in property_markers):
        return {"route": "chat", "slots": {}, "comparison": "none", "objection": "none", "reason": "farewell override"}

    fallback = _heuristic_route(text)
    heuristic = heuristic_slots(text)
    local_chat = (
        any(marker in normalized for marker in casual_markers)
        and not any(marker in normalized for marker in property_markers)
    )

    if (
        local_chat
        or fallback["route"] != "chat"
        or fallback["comparison"] != "none"
        or fallback["objection"] != "none"
        or heuristic
    ):
        return fallback

    try:
        client = Groq()

        prompt = f"""Current structured memory:
{json.dumps(state.get('slots', {}), ensure_ascii=False)}

Last shown properties:
{json.dumps(state.get('last_shown_properties', []), ensure_ascii=False)[:3000]}

User message:
{text}

Extract ONLY information explicitly stated or clearly implied by the user's
current message.

Important:
- "DHA", "DHA Defence", "Bahria", "Gulberg", "Johar Town", etc. are LOCATION values, not city values.
- "3 crore" means budget=30000000.
- If the user corrects an earlier value, return the corrected value.
- Do not invent missing values.

Return JSON only.
"""

        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": ROUTER_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
            max_tokens=300,
        )

        data = json.loads(resp.choices[0].message.content)

        data.setdefault("route", fallback["route"])
        data.setdefault("slots", {})
        data.setdefault("comparison", fallback["comparison"])
        data.setdefault("objection", fallback["objection"])
        data.setdefault("reason", "LLM router")

        llm_slots = data.get("slots") or {}
        merged_slots = dict(llm_slots)
        for key, value in heuristic.items():
            if value is not None and value != "":
                merged_slots[key] = value
        data["slots"] = merged_slots

        s = text.lower()
        if any(phrase in s for phrase in [
            "us se sasti", "usse sasti", "is se sasti", "isse sasti",
            "cheaper", "kam price", "kam mehngi", "less expensive",
            "سستی", "سستا", "اس سے سستی",
        ]):
            data["comparison"] = "cheaper"
        elif any(phrase in s for phrase in [
            "us se mehngi", "usse mehngi", "is se mehngi", "isse mehngi",
            "more expensive", "higher budget", "مہنگی", "مہنگا",
        ]):
            data["comparison"] = "more_expensive"

        if merged_slots.get("location"):
            if data["route"] == "chat":
                data["route"] = "sql"

        return data

    except Exception:
        return fallback