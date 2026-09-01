"""LangGraph-backed Day 3 conversation orchestration on top of Day 2 SQL/RAG."""

from __future__ import annotations

import json
import os
import time
from typing import TypedDict

from conversation_memory import add_turn, get_state, update_state
from day3_objections import (
    detect_objection,
    should_escalate,
    strategy,
    update_objection_counts,
)
from day3_router import route_and_extract
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
    normalized = " ".join(text.lower().split())

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
    """Forget a remembered location when the user explicitly broadens the
    search — and, when the broadening phrase names a location ("DHA kay
    ilawa koi shop"), remember that as a genuine EXCLUSION rather than
    just forgetting the filter outright.

    Those are different things: forgetting the filter means "no location
    restriction" (DHA is still a perfectly valid unrestricted match), but
    "DHA ke ilawa" means "anywhere EXCEPT DHA" — DHA must never reappear.
    The bug this fixes: "DHA kay ilawa koi shop" was popping the location
    filter to None, which still let DHA rows back into the (now
    unfiltered) result set.
    """
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
        # A fresh, non-exclusion location request supersedes any earlier
        # exclusion — otherwise asking for DHA specifically right after
        # excluding DHA would silently zero out every result (location
        # == DHA AND exclude_location == DHA can never both match).
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
        price = property_data.get("price")
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
        price = property_data.get("price")
        if price is None:
            continue
        name = property_data.get("property_type") or "Property"
        location = property_data.get("location") or property_data.get("city")
        if location:
            name = f"{name} in {location}"
        alternatives.append(f"{name}, PKR {price:,.0f}")

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
        if kind == "commercial":
            benefits = []
            if row.get("footfall_rating"):
                benefits.append(f"{row['footfall_rating']} footfall")
            if row.get("suitable_for"):
                benefits.append(f"Suitable for: {row['suitable_for']}")
            cards.append({
                "location": f"{row.get('location')}, {row.get('city')}",
                "details": f"{row.get('unit_type')}, {row.get('area_sqft')} sqft, floor {row.get('floor_number')}",
                "price": f"PKR {row['price_pkr']:,.0f}" if row.get("price_pkr") is not None else "Not verified",
                "benefits": benefits + [f"Amenities: {row.get('amenities')}"],
                "nearby_school": row.get("nearby_school", "Not available in verified data"),
                "nearby_hospital": row.get("nearby_hospital", "Not available in verified data"),
                "alternative": "Other matching commercial listings are shown below",
            })
        else:
            cards.append({
                "location": f"{row.get('location')}, {row.get('city')}",
                "details": f"{row.get('property_type')}, {row.get('bedrooms') or 'N/A'} bed, {row.get('baths') or 'N/A'} bath, {row.get('area')}",
                "price": f"PKR {row['price']:,.0f}" if row.get("price") is not None else "Not verified",
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


def _local_chat_response(text):
    normalized = " ".join(text.lower().split())
    if any(phrase in normalized for phrase in (
        "sale ya rent", "sale or rent", "ye sale hai ya rent",
        "is it sale", "is it rent",
    )):
        return "Ji, main aapko listing ka purpose bata deta hoon. Sale aur rent dono alag options hain; aap kis purpose ko prefer karte hain?"
    if any(phrase in normalized for phrase in (
        "city koi bhi", "any city", "anywhere", "all cities",
    )):
        return "Theek hai, city ki koi restriction nahi. Aapka budget aur property type bata dein, main available cities mein options dhoondhta hoon."
    if any(phrase in normalized for phrase in (
        "kya kr rhe", "kya kar rahe", "what are you doing",
    )):
        return "Main yahan aapki madad ke liye hoon. Aapki property requirements ya budget ke baare mein batayein."
    if any(phrase in normalized for phrase in (
        "pagal ho kya", "pagal hu kya", "are you crazy",
    )):
        return "Nahi ji, main yahan aapki madad ke liye hoon. Batayein, aapko kis shehar ya location mein property chahiye?"
    if any(phrase in normalized for phrase in (
        "assalam o alaikum", "assalamualaikum", "salam",
    )):
        return "Wa alaikum assalam! Main theek hoon. Aapki property requirements mein kaise madad kar sakta hoon?"
    if any(phrase in normalized for phrase in (
        "kya haal hai", "kya hal hai", "kya haal h", "kya hal h",
        "how are you", "how is life", "kya chal raha hai",
        "kya chal rha hai", "kya chal rha life", "kya chal raha life",
        "life mein kya chal raha hai", "life may kya chal rha hai",
        "aur sunao", "or sunao",
    )):
        return "Main theek hoon, shukriya! Aapki property requirements mein kaise madad kar sakta hoon?"
    if normalized in {"okay", "ok", "theek hai", "thanks", "thank you"}:
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
            price = f"PKR {row['price_pkr']:,.0f}" if row.get("price_pkr") is not None else "price verify nahi hai"
            parts.append(
                f"{row.get('unit_type')} {row.get('location')}, {row.get('city')} "
                f"({row.get('area_sqft')} sqft, {price})"
            )
        else:
            price = f"PKR {row['price']:,.0f}" if row.get("price") is not None else "price verify nahi hai"
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

    # --- FIX: a rent budget and a sale budget are never interchangeable.
    # If this turn's router output names a NEW purpose that differs from
    # whatever purpose was already in memory, any budget left over from
    # the old purpose is stale and must be dropped - unless this same
    # turn also supplies a fresh budget, in which case that new value
    # already wins in the merge below and must NOT be wiped.
    # Root cause this fixes: "rent a house ... budget 2 lac" (purpose=
    # For Rent, budget=200000) followed later by "for sale flats"
    # (purpose flips to For Sale, no number said) kept budget=200000
    # attached to a For Sale query. Since build_database() nulls out any
    # For Sale row below MIN_PLAUSIBLE_SALE_PRICE (1,000,000), that
    # combination can never match a single row - so "for sale flats",
    # and every bare follow-up city name after it, silently returned
    # "no matching listing" until the user stated a brand-new number.
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

    query = s["user_text"]
    slots = _clear_replaced_location(slots, query)
    s["memory"]["slots"] = slots
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

    commercial_terms = ("shop", "office", "warehouse", "plaza", "commercial")
    is_commercial = any(term in query.lower() for term in commercial_terms)

    rent_words = ("rent", "kiraya", "kiraye", "rental")
    effective_purpose = slots.get("purpose") or (
        "For Rent" if any(w in query.lower() for w in rent_words) else "For Sale"
    )
    facility_request = any(word in query.lower() for word in ("school", "hospital", "nearby"))

    # Same idea as effective_purpose above, but for the four actual
    # unit_type values in commercial_properties (Shop / Office /
    # Warehouse / Plaza Floor). Previously nothing extracted this at
    # all, so asking for "shop" or "office" specifically had zero effect
    # on the query — a "shop in Lahore" request could just as easily
    # come back full of Offices and Warehouses.
    commercial_unit_type_map = {
        "shop": "Shop",
        "dukan": "Shop",
        "office": "Office",
        "warehouse": "Warehouse",
        "godown": "Warehouse",
        "plaza": "Plaza Floor",
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
        if not results and detected_unit_type:
            results = query_commercial(
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
"""

    objection_category = s["objection_category"]
    normalized_query = " ".join(query.lower().split())

    if s.get("is_reference_query"):
        shown_rows = s.get("last_shown", [])
        last_kind = s["memory"].get("last_shown_kind", "residential")

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
                from day3_agent import _amenity_followup_response
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
            "Ji, samajh sakta hoon. Aap kis area ya location ko prefer karte hain? "
            "Main us preference ke mutabiq verified options dekh leta hoon."
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


def run_turn(session_id, user_text):
    memory = get_state(session_id)

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