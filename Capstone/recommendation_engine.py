"""
Week 7 - Day 2 - Task 4: Property Recommendation Engine
==========================================================
Recommends properties by BUDGET, CITY, AREA, BEDROOMS, PURPOSE, AMENITIES,
and INVESTMENT GOALS.

Design: this is a two-stage funnel, not a single query -
  Stage 1 (SQL, hard filters): budget/city/bedrooms/purpose - things that
    are pass/fail. A 5-bed house doesn't "sort of" match a 3-bed request.
  Stage 2 (scoring, soft preferences): amenities + investment-goal fit -
    these are weighted, not filtered, because a great property missing one
    amenity shouldn't be thrown out entirely.

Investment-goal handling: "investment" purpose properties get scored higher
if they're in areas tagged as high-growth (this list should eventually come
from your own market data - it's a placeholder set of currently popular
Pakistani investment corridors for demo purposes).
"""

from structured_retrieval import query_properties, query_commercial, format_as_context

# Placeholder - replace with real appreciation/rental-yield data once available
HIGH_GROWTH_AREAS = {"Bahria Town", "DHA Phase 9", "DHA Phase 5", "Gwadar", "Bahria Orchard"}

AMENITY_WEIGHT = 10       # points per matched amenity
GROWTH_AREA_BONUS = 25    # points if investment-flagged and in a growth area


def recommend_properties(budget_max=None, budget_min=None, city=None, bedrooms=None,
                          purpose="For Sale", property_type=None, desired_amenities=None,
                          investment_goal=False, top_n=5):
    """
    Returns a ranked list of {property, score, reasons} dicts.
    """
    desired_amenities = desired_amenities or []

    # Stage 1: hard SQL filter (over-fetch a bit so scoring has something to rank)
    candidates = query_properties(
        city=city, purpose=purpose, min_price=budget_min, max_price=budget_max,
        bedrooms=bedrooms, property_type=property_type, limit=30,
    )

    if not candidates:
        return []

    # Stage 2: soft scoring
    scored = []
    for prop in candidates:
        score = 0
        reasons = []

        # amenity match - property_amenities lookup would join here in the real DB;
        # placeholder assumes an 'amenities' text column exists on the property row
        prop_amenities = str(prop.get("amenities", "")).lower()
        matched = [a for a in desired_amenities if a.lower() in prop_amenities]
        if matched:
            score += len(matched) * AMENITY_WEIGHT
            reasons.append(f"Has {', '.join(matched)}")

        if investment_goal:
            location = prop.get("location", "")
            if any(area.lower() in location.lower() for area in HIGH_GROWTH_AREAS):
                score += GROWTH_AREA_BONUS
                reasons.append(f"{location} is a high-growth investment corridor")

        # budget efficiency: reward being well under max budget, not just under it
        if budget_max and prop.get("price"):
            headroom = (budget_max - prop["price"]) / budget_max
            score += max(0, headroom) * 15
            if headroom > 0.15:
                reasons.append("Comfortably within your budget")

        scored.append({"property": prop, "score": round(score, 1), "reasons": reasons})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_n]


def recommend_commercial(budget_max=None, city=None, unit_type=None, suitable_for=None, top_n=5):
    candidates = query_commercial(city=city, unit_type=unit_type, max_price=budget_max,
                                   suitable_for=suitable_for, limit=top_n)
    return [{"property": c, "score": None, "reasons": []} for c in candidates]


def explain_recommendations(results, kind="residential"):
    """Formats recommendations into UrduLish-ready context for the LLM to speak from."""
    if not results:
        return "Sir, is criteria par abhi koi property available nahi hai - main aap ke liye similar options dhoond sakta hoon."
    lines = []
    for r in results:
        p = r["property"]
        base = format_as_context([p], kind=kind)
        reason = f" ({'; '.join(r['reasons'])})" if r.get("reasons") else ""
        lines.append(base + reason)
    return "\n".join(lines)


if __name__ == "__main__":
    results = recommend_properties(
        budget_max=25_000_000, city="Lahore", bedrooms=3, purpose="For Sale",
        desired_amenities=["Park", "Security"], investment_goal=False,
    )
    print(explain_recommendations(results))
