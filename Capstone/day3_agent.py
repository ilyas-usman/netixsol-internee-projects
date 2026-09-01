"""LangGraph-backed Day 3 conversation orchestration on top of Day 2 SQL/RAG."""

from __future__ import annotations

import json
import os
import time
from typing import TypedDict

from conversation_memory import add_turn, get_state, update_state
from day3_objections import (
    detect_objection,
    normalize_text,
    should_escalate,
    strategy,
    update_objection_counts,
)
from day3_router import FAREWELL_MARKERS, route_and_extract
from rag_pipeline import (
    chunk_documents,
    generate_answer,
    generate_grounded_reply,
    index_chunks,
    load_documents,
    retrieve,
)
from structured_retrieval import (
    enrich_listing_rows,
    format_as_context,
    format_price_pkr,
    query_commercial,
    query_properties,
)

try:
    from groq import Groq
except ImportError:
    Groq = None

try:
    from langgraph.graph import END, START, StateGraph
except ImportError:
    StateGraph = None
    START = END = None

# Week 7 Day 4 addition (purely additive): appointment booking/reschedule/
# cancellation. Guarded the same way Groq/StateGraph are above so a missing
# optional dependency can never break the Day 2/Day 3 conversation path.
try:
    from appointment_agent import handle_appointment_turn
except ImportError:
    def handle_appointment_turn(session_id, user_text, memory, known_phone=None):
        return None

# Week 7 Day 4 Task 5 addition (purely additive): CRM — client history/
# profile lookup, follow-up reminders, and unconditional transcript +
# preference logging. Same optional-dependency guard as above.
try:
    from crm_agent import handle_crm_turn, log_turn_to_crm
except ImportError:
    def handle_crm_turn(session_id, user_text, memory):
        return None

    def log_turn_to_crm(*args, **kwargs):
        pass


_docs = load_documents("./knowledge_docs")
_chunks = chunk_documents(_docs, chunk_size=400)

if _chunks:
    from rag_pipeline import get_collection

    _collection = get_collection(reset=False)

    if _collection.count() == 0:
        _collection = index_chunks(_chunks, reset=False)
else:
    _collection = None


class AgentState(TypedDict, total=False):
    session_id: str
    user_text: str
    memory: dict
    route: dict
    sql_context: str
    rag_hits: list
    response: str
    timings: dict
    objection_category: str
    escalation: bool
    last_shown: list
    listings: list


def _merge_slots(old, new):
    result = dict(old or {})
    new = new or {}

    new_city = new.get("city")
    new_location = new.get("location")
    old_city = result.get("city")

    if new_city and not new_location and new_city != old_city:
        result.pop("location", None)

    for key, value in new.items():
        if value is not None and value != "":
            result[key] = value

    return result


REFERENCE_PHRASES = (
    "inmay se", "inmay say", "in mein se", "in mein say", "in mai se",
    "unmein se", "un mein se", "un mein say", "isme se", "is mein se",
    "inme se", "in options mein se", "ye wale", "in mein", "unme se",
    "of these", "among these", "which of these", "which one of these",
    "what about", "iske baare mein", "is ke baare mein", "in ke baare mein",
    "inke baare mein", "un ke baare mein", "unke baare mein",
    # Urdu script equivalents
    "ان میں سے", "ان میں", "ان سے", "اس سے", "ان کا", "ان کی", "اس کا", "اس کی",
    "ان فلیٹ", "ان فلیٹس", "ان گھر", "ان گھروں", "اس گھر", "اس فلیٹ", "یہ فلیٹ", "یہ گھر",
)

REFERENCE_PRONOUN_MARKERS = (
    "are they", "is it", "are these", "is this", "are those", "is that",
    "kya ye", "kya wo", "kya yeh", "kya woh", "inka", "unka", "iska", "uska",
    "کیا یہ", "کیا وہ", "ان کا", "ان کی", "اس کا", "اس کی",
)

AMENITY_FOLLOWUP_MARKERS = (
    "utilities", "utility", "amenities", "amenity", "facilities", "facility",
    "area", "sahulat", "سہولیات", "سہولت", "یوٹیلٹیز", "یوٹیلیٹی", "اسکول", "سکول",
    "ہاسپٹل", "ہسپتال", "کتنا دور", "کتنے دور", "کتنی دور", "دور ہے", "دور ہیں", "قریب",
)


def _is_reference_to_shown(text, new_slots=None):
    normalized = normalize_text(text)

    if any(phrase in normalized for phrase in REFERENCE_PHRASES):
        return True

    if any(marker in normalized for marker in REFERENCE_PRONOUN_MARKERS):
        new_slots = new_slots or {}
        no_new_entity = not any(
            new_slots.get(k) for k in ("city", "location", "property_type", "bedrooms")
        )
        if no_new_entity:
            return True

    if any(marker in normalized for marker in AMENITY_FOLLOWUP_MARKERS):
        new_slots = new_slots or {}
        no_new_entity = not any(
            new_slots.get(k) for k in ("city", "location", "property_type", "bedrooms", "budget")
        )
        if no_new_entity:
            return True

    return False


def _clear_replaced_location(slots, text):
    normalized = " ".join(text.lower().split())
    reset_phrases = (
        "ke ilawa", "kay ilawa", "ke alawa", "kay alawa",
        "other than", "apart from", "except",
        "rather than", "raher then", "rather then",
    )
    has_exclusion_phrase = any(phrase in normalized for phrase in reset_phrases)
    if has_exclusion_phrase:
        excluded = slots.get("location")
        if excluded:
            slots["exclude_location"] = excluded
        slots.pop("location", None)
    elif slots.get("location"):
        slots.pop("exclude_location", None)
    if any(phrase in normalized for phrase in (
        "city koi bhi", "any city", "anywhere", "all cities",
    )):
        slots.pop("city", None)
    if any(phrase in normalized for phrase in (
        "sale ya rent", "sale or rent", "ye sale hai ya rent",
    )):
        slots.pop("purpose", None)
    return slots


def _get_reference_price(properties):
    if not properties:
        return None

    for property_data in reversed(properties):
        price = property_data.get("price") if property_data.get("price") is not None else property_data.get("price_pkr")
        if price is not None:
            return price

    return None


def _price_objection_response(properties):
    if not properties:
        return (
            "Ji, samajh sakta hoon. Is waqt mujhe aapki requirements ke mutabiq "
            "koi sasta verified option nahi mila. Aap apna maximum budget bata dein."
        )

    alternatives = []
    for property_data in properties[:3]:
        price = property_data.get("price") if property_data.get("price") is not None else property_data.get("price_pkr")
        if price is None:
            continue
        name = property_data.get("property_type") or property_data.get("unit_type") or "Property"
        location = property_data.get("location") or property_data.get("city")
        if location:
            name = f"{name} in {location}"
        alternatives.append(f"{name}, PKR {format_price_pkr(price)}")

    if not alternatives:
        return (
            "Ji, samajh sakta hoon. Mujhe is waqt koi aisa verified option nahi mila "
            "jiski price confirm ho. Aap apna maximum budget bata dein."
        )

    return (
        "Ji, samajh sakta hoon. Maine kam price ke verified options dekhe hain: "
        + "; ".join(alternatives)
        + "."
    )


def _listing_cards(rows, kind):
    cards = []
    for row in rows:
        val_price = row.get("price") if row.get("price") is not None else row.get("price_pkr")
        if kind == "commercial":
            benefits = []
            if row.get("footfall_rating"):
                benefits.append(f"{row['footfall_rating']} footfall")
            if row.get("suitable_for"):
                benefits.append(f"Suitable for: {row['suitable_for']}")
            cards.append({
                "location": f"{row.get('location')}, {row.get('city')}",
                "details": f"{row.get('unit_type')}, {row.get('area_sqft')} sqft, floor {row.get('floor_number')}",
                "price": f"PKR {format_price_pkr(val_price)}" if val_price is not None else "Not verified",
                "benefits": benefits + [f"Amenities: {row.get('amenities')}"],
                "nearby_school": row.get("nearby_school", "Not available in verified data"),
                "nearby_hospital": row.get("nearby_hospital", "Not available in verified data"),
                "alternative": "Other matching commercial listings are shown below",
            })
        else:
            cards.append({
                "location": f"{row.get('location')}, {row.get('city')}",
                "details": f"{row.get('property_type')}, {row.get('bedrooms') or 'N/A'} bed, {row.get('baths') or 'N/A'} bath, {row.get('area')}",
                "price": f"PKR {format_price_pkr(val_price)}" if val_price is not None else "Not verified",
                "benefits": [
                    f"Purpose: {row.get('purpose') or 'Not available'}",
                    f"Agent: {row.get('agent') or 'Not listed'}",
                    f"Amenities: {row.get('amenities', 'Not available in verified data')}",
                ],
                "nearby_school": row.get("nearby_school", "Not available in verified data"),
                "nearby_hospital": row.get("nearby_hospital", "Not available in verified data"),
                "alternative": "Other matching listings are shown below",
            })
    return cards


def _amenity_followup_response(rows, kind):
    if not rows:
        return "Ji, is baare mein mere paas koi shown listing nahi hai — pehle property search karein."
    parts = []
    for row in rows[:5]:
        loc = f"{row.get('location')}, {row.get('city')}"
        amenities = row.get("amenities") or "Not available in verified data"
        school = row.get("nearby_school", "Not available in verified data")
        hospital = row.get("nearby_hospital", "Not available in verified data")
        price = format_price_pkr(row.get("price") if kind == "residential" else row.get("price_pkr"))
        parts.append(
            f"{loc} (PKR {price}): amenities - {amenities}; nearby school - {school}; nearby hospital - {hospital}"
        )
    return "Ji bilkul, in listings ki details ye hain: " + " | ".join(parts) + "."


def _local_chat_response(text):
    normalized = normalize_text(text)
    if any(phrase in normalized for phrase in (
        "sale ya rent", "sale or rent", "ye sale hai ya rent",
        "is it sale", "is it rent",
    )):
        return "Ji, main aapko listing ka purpose bata deta hoon. Sale aur rent dono alag options hain; aap kis purpose ko prefer karte hain?"
    if any(phrase in normalized for phrase in (
        "city koi bhi", "any city", "anywhere", "all cities",
    )):
        return "Theek hai, city ki koi restriction nahi. Aapka budget aur property type bata dein, main available cities mein options dhoondhta hoon."
    if any(phrase in normalized for phrase in FAREWELL_MARKERS):
        return "Allah Hafiz sir! RealEstate Hub se baat karne ka shukriya. Aapka din accha guzre!"
    if any(phrase in normalized for phrase in (
        "kya kr rhe", "kya kar rahe", "what are you doing",
    )):
        return "Main yahan aapki madad ke liye hoon. Aapki property requirements ya budget ke baare mein batayein."
    if any(phrase in normalized for phrase in (
        "pagal ho kya", "pagal hu kya", "are you crazy",
    )):
        return "Nahi ji, main yahan aapki madad ke liye hoon. Batayein, aapko kis shehar ya location mein property chahiye?"
    if any(phrase in normalized for phrase in (
        "assalam o alaikum", "assalamualaikum", "salam", "السلام علیکم", "سلام",
    )):
        return "Wa alaikum assalam! Main theek hoon. Aapki property requirements mein kaise madad kar sakta hoon?"
    if any(phrase in normalized for phrase in (
        "kya haal hai", "kya hal hai", "kya haal h", "kya hal h",
        "how are you", "how is life", "kya chal raha hai",
        "kya chal rha hai", "kya chal rha life", "kya chal raha life",
        "life mein kya chal raha hai", "life may kya chal rha hai",
        "aur sunao", "or sunao", "کیا حال ہے", "کیسے ہیں",
    )):
        return "Main theek hoon, shukriya! Aapki property requirements mein kaise madad kar sakta hoon?"
    if normalized in {"okay", "ok", "theek hai", "thanks", "thank you", "شکریہ"}:
        return "Theek hai. Aap apna budget, city, location, ya property type bata dein."
    if any(phrase in normalized for phrase in ("koi option do", "show me options", "options dikhao")):
        return "Ji bilkul. Options dhoondhne ke liye apna budget aur preferred city ya location bata dein."
    return "Ji bilkul. Aap apna budget, city, location, ya property type bata dein."


def _verified_listing_response(rows, kind, slots=None):
    if not rows:
        slots = slots or {}
        requested = " ".join(
            str(value) for value in (slots.get("city"), slots.get("location"))
            if value
        ) or "is request"
        return f"Ji, {requested} ke liye hamare verified database mein koi matching listing nahi mili. Aap city, budget, ya property type adjust karna chahein to bata dein."
    parts = []
    for row in rows[:5]:
        if kind == "commercial":
            price = f"PKR {format_price_pkr(row.get('price_pkr'))}" if row.get("price_pkr") is not None else "price verify nahi hai"
            parts.append(
                f"{row.get('unit_type')} {row.get('location')}, {row.get('city')} "
                f"({row.get('area_sqft')} sqft, {price})"
            )
        else:
            price = f"PKR {format_price_pkr(row.get('price'))}" if row.get("price") is not None else "price verify nahi hai"
            details = [str(row.get("property_type"))]
            if row.get("bedrooms") not in (None, 0):
                details.append(f"{int(row['bedrooms'])} bed")
            if row.get("area"):
                details.append(str(row["area"]))
            parts.append(f"{row.get('location')}, {row.get('city')} ({', '.join(details)}, {price})")
    return "Ji bilkul, verified options ye hain: " + "; ".join(parts) + "."


def node_route(s: AgentState):
    t = time.perf_counter()

    s["route"] = route_and_extract(
        s["user_text"],
        s["memory"],
    )

    s.setdefault("timings", {})["router_ms"] = (
        time.perf_counter() - t
    ) * 1000

    return s


def node_retrieve(s: AgentState):
    t = time.perf_counter()

    route = s["route"]
    query = s["user_text"]
    normalized_query = normalize_text(query)

    old_purpose = (s["memory"].get("slots") or {}).get("purpose")
    incoming_slots = route.get("slots") or {}
    new_purpose = incoming_slots.get("purpose")
    purpose_changed = bool(new_purpose) and bool(old_purpose) and new_purpose != old_purpose

    slots = _merge_slots(
        s["memory"].get("slots"),
        route.get("slots"),
    )

    if purpose_changed and not incoming_slots.get("budget"):
        slots.pop("budget", None)

    slots = _clear_replaced_location(slots, query)
    s["memory"]["slots"] = slots

    # Force clean state for farewell / small chat turns
    if route.get("route") == "chat" or any(marker in normalized_query for marker in FAREWELL_MARKERS):
        s["sql_context"] = ""
        s["last_shown"] = []
        s["listings"] = []
        s["rag_hits"] = []
        s["is_reference_query"] = False
        s["timings"]["retrieve_ms"] = (time.perf_counter() - t) * 1000
        return s
    sql_context = ""
    shown = s["memory"].get("last_shown_properties", [])
    listings = []

    comparison = route.get("comparison", "none")
    budget = slots.get("budget")

    if _is_reference_to_shown(query, route.get("slots")) and shown:
        last_kind = s["memory"].get("last_shown_kind", "residential")
        s["sql_context"] = format_as_context(shown, kind=last_kind)
        s["last_shown"] = shown
        s["listings"] = _listing_cards(shown, last_kind)
        s["rag_hits"] = []
        s["is_reference_query"] = True
        s["timings"]["retrieve_ms"] = (time.perf_counter() - t) * 1000
        return s

    s["is_reference_query"] = False

    if comparison == "cheaper" or route.get("objection") == "price":
        previous_properties = s["memory"].get(
            "last_shown_properties",
            [],
        )

        reference_price = _get_reference_price(previous_properties)

        if reference_price is not None:
            budget = max(0, reference_price - 1)

    commercial_terms = (
        "shop", "office", "warehouse", "plaza", "commercial",
        "dukan", "dokaan", "دکان", "شاپ", "کمرشل", "دفتر", "آفس"
    )
    is_commercial = any(term in query.lower() for term in commercial_terms) or slots.get("property_type") in ("Shop", "Office", "Commercial Plot", "Commercial")

    if is_commercial:
        slots.pop("bedrooms", None)
        if slots.get("property_type") in ("House", "Flat", "Apartment", "Plot", "Farm House", "Room"):
            slots.pop("property_type", None)

    rent_words = ("rent", "kiraya", "kiraye", "rental", "کرایہ", "کرائے", "رینٹ")
    effective_purpose = slots.get("purpose") or (
        "For Rent" if any(w in query.lower() for w in rent_words) else "For Sale"
    )
    facility_request = any(word in query.lower() for word in ("school", "hospital", "nearby", "سکول", "ہسپتال", "قریب"))

    commercial_unit_type_map = {
        "shop": "Shop",
        "dukan": "Shop",
        "dokaan": "Shop",
        "دکان": "Shop",
        "شاپ": "Shop",
        "office": "Office",
        "daftar": "Office",
        "دفتر": "Office",
        "آفس": "Office",
        "warehouse": "Warehouse",
        "godown": "Warehouse",
        "ویئر ہاؤس": "Warehouse",
        "plaza": "Plaza Floor",
        "پلازہ": "Plaza Floor",
    }
    detected_unit_type = None
    for term, mapped in commercial_unit_type_map.items():
        if term in query.lower():
            detected_unit_type = mapped
            break

    if route["route"] in ("sql", "both") and is_commercial:
        results = query_commercial(
            city=slots.get("city"),
            location=slots.get("location"),
            exclude_location=slots.get("exclude_location"),
            unit_type=detected_unit_type,
            purpose=effective_purpose,
            max_price=budget,
            limit=5,
        )
        if not results and (detected_unit_type or budget or slots.get("location")):
            results = query_commercial(
                city=slots.get("city"),
                purpose=effective_purpose,
                limit=5,
            )
        shown = enrich_listing_rows(results)
        filtered_facility = shown
        if "school" in query.lower() or "سکول" in query.lower():
            filtered_facility = [row for row in filtered_facility if row.get("nearby_school") != "Not available in verified data"]
        if "hospital" in query.lower() or "ہسپتال" in query.lower():
            filtered_facility = [row for row in filtered_facility if row.get("nearby_hospital") != "Not available in verified data"]
        
        results = filtered_facility if filtered_facility else shown
        sql_context = format_as_context(results, kind="commercial")
        listings = _listing_cards(results, "commercial")
        s["memory"]["last_shown_kind"] = "commercial"
    elif route["route"] in ("sql", "both"):
        if facility_request and not slots.get("purpose") and not any(w in query.lower() for w in rent_words):
            sale_rows = query_properties(
                city=slots.get("city"), location=slots.get("location"),
                exclude_location=slots.get("exclude_location"),
                purpose="For Sale", max_price=budget,
                bedrooms=slots.get("bedrooms"), property_type=slots.get("property_type"), limit=5,
            )
            rent_rows = query_properties(
                city=slots.get("city"), location=slots.get("location"),
                exclude_location=slots.get("exclude_location"),
                purpose="For Rent", max_price=budget,
                bedrooms=slots.get("bedrooms"), property_type=slots.get("property_type"), limit=5,
            )
            results = sale_rows + rent_rows
        else:
            results = query_properties(
                city=slots.get("city"), location=slots.get("location"),
                exclude_location=slots.get("exclude_location"),
                purpose=effective_purpose, max_price=budget,
                bedrooms=slots.get("bedrooms"), property_type=slots.get("property_type"), limit=5,
            )

        if not results and route.get("route") == "sql" and not slots.get("location"):
            results = query_properties(
                city=slots.get("city"),
                location=slots.get("location"),
                exclude_location=slots.get("exclude_location"),
                purpose=effective_purpose,
                max_price=budget,
                limit=5,
            )

        shown = enrich_listing_rows(results)
        results = shown
        if "school" in query.lower():
            results = [row for row in results if row.get("nearby_school") != "Not available in verified data"]
        if "hospital" in query.lower():
            results = [row for row in results if row.get("nearby_hospital") != "Not available in verified data"]
        shown = results

        sql_context = format_as_context(
            results,
            kind="residential",
        )
        listings = _listing_cards(results, "residential")
        s["memory"]["last_shown_kind"] = "residential"

    if route["route"] in ("rag", "both") and _collection:
        s["rag_hits"] = retrieve(
            query,
            _collection,
            k=4,
        )
    else:
        s["rag_hits"] = []

    s["sql_context"] = sql_context
    s["last_shown"] = shown
    s["listings"] = listings

    s["timings"]["retrieve_ms"] = (
        time.perf_counter() - t
    ) * 1000

    return s


def node_objection(s: AgentState):
    category = (
        detect_objection(s["user_text"])
        or s["route"].get("objection", "none")
    )

    s["objection_category"] = category

    objections = update_objection_counts(
        s["memory"].get("objections", {}),
        category,
    )

    s["memory"]["objections"] = objections

    s["escalation"] = should_escalate(
        objections,
        category,
    )

    return s


def node_generate(s: AgentState):
    t = time.perf_counter()

    query = s["user_text"]
    route = s["route"]

    if (
        route["route"] == "chat"
        and s["objection_category"] == "none"
    ):
        hits = []
    else:
        hits = s.get("rag_hits", [])

    structured = s.get("sql_context") or None

    context_note = ""

    if s["objection_category"] != "none":
        context_note = (
            f"\nObjection category: {s['objection_category']}. "
            f"Strategy: {strategy(s['objection_category'])}"
        )

    if s["escalation"]:
        context_note += (
            "\nESCALATE: this objection has remained unresolved "
            "twice. Offer a human agent."
        )

    if s.get("memory", {}).get("history"):
        recent = s["memory"]["history"][-6:]

        history = "\n".join(
            f"{item['role']}: {item['text']}"
            for item in recent
        )
    else:
        history = ""

    persistent_slots = s["memory"].get("slots", {})

    extra_instructions = f"""Conversation history:
{history}

Persistent slots:
{json.dumps(persistent_slots, ensure_ascii=False)}

{context_note}

Voice rules:
- Speak in natural Pakistani UrduLish, concise 1-3 spoken sentences.
- Use acknowledgements/fillers naturally, not every turn:
  'Ji bilkul', 'Acha', 'Hmm', 'Ek second sir'.
- Do not use markdown, bullets, or stage directions.
- Never invent prices, availability, facilities, payment terms,
  developer claims, or investment returns.
- When the user asks for a cheaper option, use the verified SQL
  results and do not repeat a property that is not cheaper.
- State all PKR amounts in lakh/crore words (e.g. "57 lakh",
  "2 crore 10 lakh") exactly as given in the context - never as a
  raw digit string, and never re-derive or reformat a number
  yourself.
"""

    objection_category = s["objection_category"]
    normalized_query = normalize_text(query)

    # Handle farewells immediately
    if any(phrase in normalized_query for phrase in FAREWELL_MARKERS):
        s["response"] = _local_chat_response(query)
        s["listings"] = []
        s["timings"]["llm_ms"] = 0
        s["timings"]["total_ms"] = sum(s["timings"].values())
        return s

    if s.get("is_reference_query"):
        shown_rows = s.get("last_shown", [])
        last_kind = s["memory"].get("last_shown_kind", "residential")

        wants_purpose_breakdown = any(
            w in normalized_query for w in ("rent", "kiraya", "kiraye", "buy", "sale", "khareed")
        )
        # FIX: new branch. Previously an amenity/utilities/area follow-up
        # ("what about area?utilities?") either never reached this function
        # at all (is_reference_query was False - see REFERENCE_PHRASES fix
        # above) or, once it did, would have fallen into the generic
        # _verified_listing_response() dump below, which repeats full
        # listing blocks but never directly answers an amenities question.
        # Checked BEFORE wants_purpose_breakdown since an amenity question
        # is more specific and shouldn't be misread as a purpose question.
        wants_amenities = any(w in normalized_query for w in (
            "utilities", "utility", "amenities", "amenity", "facilities",
            "facility", "area", "sahulat", "سہولیات", "سہولت", "اسکول", "سکول",
            "ہاسپٹل", "ہسپتال", "کتنا دور", "کتنے دور", "کتنی دور", "دور ہے", "دور ہیں",
            "یوٹیلٹیز", "یوٹیلیٹی", "قریب", "نزدیک", "school", "hospital", "distance",
            "near", "kareeb", "karib",
        ))

        if wants_amenities:
            try:
                response = generate_grounded_reply(
                    query,
                    hits,
                    structured_context=format_as_context(shown_rows, last_kind),
                    extra_instructions=extra_instructions + "\nSpecifically answer the user's question about nearby schools, hospitals, utilities, or facility distances using the verified listing facts.",
                )
            except Exception:
                response = _amenity_followup_response(shown_rows, last_kind)
        elif wants_purpose_breakdown and last_kind == "residential":
            rent_ones = [r for r in shown_rows if r.get("purpose") == "For Rent"]
            sale_ones = [r for r in shown_rows if r.get("purpose") == "For Sale"]
            parts = []
            if rent_ones:
                parts.append(
                    "Rent ke liye: " + "; ".join(
                        f"{r.get('property_type')} {r.get('location')}" for r in rent_ones
                    )
                )
            if sale_ones:
                parts.append(
                    "Buy/Sale ke liye: " + "; ".join(
                        f"{r.get('property_type')} {r.get('location')}" for r in sale_ones
                    )
                )
            response = (
                " ".join(parts) if parts else
                "Ji, in listings ka sale ya rent purpose verified data mein available nahi hai."
            )
        elif wants_purpose_breakdown and last_kind == "commercial":
            response = (
                "Ji, in commercial listings ke liye rent ya sale ka status "
                "verified data mein tag nahi hai — main confirm karke batata hoon."
            )
        else:
            response = _verified_listing_response(shown_rows, last_kind)

        s["response"] = response
        s["timings"]["llm_ms"] = 0
        s["timings"]["total_ms"] = sum(s["timings"].values())
        return s

    if any(phrase in normalized_query for phrase in (
        "sale ya rent", "sale or rent", "ye sale hai ya rent",
    )):
        previous = s["memory"].get("last_shown_properties", [])
        purposes = sorted({row.get("purpose") for row in previous if row.get("purpose")})
        if purposes:
            response = "Ji, pichli shown listings ka purpose: " + ", ".join(purposes) + "."
        else:
            response = "Ji, is listing ka sale ya rent purpose verified data mein available nahi hai."
        s["response"] = response
        s["timings"]["llm_ms"] = 0
        s["timings"]["total_ms"] = sum(s["timings"].values())
        return s

    if objection_category == "price":
        response = _price_objection_response(s.get("last_shown", []))
    elif objection_category == "location":
        response = (
            "Ji, samajh sakta hoon location bilkul convenient honi chahiye. "
            "Pichli shown listings main market aur access roads ke kareeb hain. "
            "Aap kis specific area ko prefer karte hain?"
        )
    elif objection_category == "trust":
        response = (
            "Ji bilkul, aapka concern genuine hai. Hum sirf 100% verified developers "
            "aur legal properties show karte hain. Aap direct document verification demand kar sakte hain."
        )
    elif objection_category == "investment":
        response = (
            "Ji, investment ke hawale se ye high-growth corridors hain jahan "
            "rental yield aur capital appreciation positive hai."
        )
    elif objection_category == "builder":
        response = (
            "Ji, is project ke builder ka track record fully verified hai. "
            "Delivery timeline aur construction quality certified standards ke mutabiq hain."
        )
    elif objection_category == "maintenance":
        response = (
            "Ji, maintenance charges verified listings mein clearly listed hain. "
            "Monthly maintenance fee budget-friendly hai aur standard services include karti hai."
        )

    elif route["route"] == "chat":
        response = _local_chat_response(query)

    elif route["route"] in ("sql", "both") and s.get("last_shown"):
        response = _verified_listing_response(
            s["last_shown"],
            "commercial" if any(term in normalized_query for term in ("shop", "office", "warehouse", "plaza", "commercial")) else "residential",
        )

    elif route["route"] in ("sql", "both"):
        response = _verified_listing_response(
            [],
            "commercial" if any(term in normalized_query for term in ("shop", "office", "warehouse", "plaza", "commercial")) else "residential",
            s["memory"].get("slots", {}),
        )

    else:
        response = generate_grounded_reply(
            query,
            hits,
            structured_context=structured,
            extra_instructions=extra_instructions,
        )

    if s["escalation"]:
        response = (
            response.rstrip()
            + " Agar aap chahein to main aap ko "
              "human property consultant se connect karwa deta hoon."
        )

    s["response"] = response

    s["timings"]["llm_ms"] = (
        time.perf_counter() - t
    ) * 1000

    s["timings"]["total_ms"] = sum(
        s["timings"].values()
    )

    return s


def _build_graph():
    if StateGraph is None:
        return None

    graph = StateGraph(AgentState)

    graph.add_node("route", node_route)
    graph.add_node("retrieve", node_retrieve)
    graph.add_node("objection", node_objection)
    graph.add_node("generate", node_generate)

    graph.add_edge(START, "route")
    graph.add_edge("route", "retrieve")
    graph.add_edge("retrieve", "objection")
    graph.add_edge("objection", "generate")
    graph.add_edge("generate", END)

    return graph.compile()


GRAPH = _build_graph()


def run_turn(session_id, user_text, known_phone=None):
    memory = get_state(session_id)

    # Week 7 Day 4 Task 5 addition: CRM commands (client history/profile,
    # follow-up reminders). Checked first but only actually claims the turn
    # when a command keyword matches AND no appointment flow already owns
    # this session (see has_active_draft() inside crm_agent), so it can
    # never hijack a booking/reschedule/cancel in progress.
    crm_result = handle_crm_turn(session_id, user_text, memory)

    # Week 7 Day 4 addition: appointment booking/reschedule/cancellation.
    # Purely additive short-circuit — handle_appointment_turn returns None
    # unless the message (or an appointment flow already in progress for
    # this session) is actually appointment-related, in which case every
    # line below runs exactly as it did in Day 3, unchanged.
    # known_phone: optional caller-ID style number from the calling channel
    # (e.g. a real Vapi phone call) — defaults to None everywhere else, so
    # every existing caller of run_turn(session_id, user_text) is unaffected.
    appt_result = None if crm_result is not None else handle_appointment_turn(session_id, user_text, memory, known_phone=known_phone)

    if crm_result is not None:
        result = crm_result
    elif appt_result is not None:
        result = appt_result
    else:
        initial = {
            "session_id": session_id,
            "user_text": user_text,
            "memory": memory,
            "timings": {},
        }

        result = (
            GRAPH.invoke(initial)
            if GRAPH
            else _fallback_turn(initial)
        )

    # Week 7 Day 4 Task 5 addition: log every turn (call transcript) and
    # merge any known client preferences, regardless of which route handled
    # it. Defensive by construction — log_turn_to_crm never raises past
    # this point for a missing/failed CRM layer.
    try:
        log_turn_to_crm(session_id, user_text, result, memory)
    except Exception:
        pass

    slots = result["memory"]["slots"]

    update_state(
        session_id,
        slots=slots,
        last_shown_properties=result.get(
            "last_shown",
            memory.get("last_shown_properties", []),
        ),
        objections=result["memory"].get(
            "objections",
            memory.get("objections", {}),
        ),
    )

    add_turn(
        session_id,
        "user",
        user_text,
        {
            "route": result["route"],
            "slots": slots,
        },
    )

    add_turn(
        session_id,
        "assistant",
        result["response"],
        {
            "timings": result["timings"],
            "objection": result.get("objection_category"),
        },
    )

    return result


def _fallback_turn(s):
    s = node_route(s)
    s = node_retrieve(s)
    s = node_objection(s)
    s = node_generate(s)
    return s