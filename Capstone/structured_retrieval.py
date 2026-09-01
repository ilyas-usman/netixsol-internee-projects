"""
Week 7 - Day 2 - Task 3: Structured Retrieval
================================================
Loads the Zameen.com CSV (+ dummy commercial CSV) into SQLite and exposes
query functions for the "hard fact" fields. Paired with rag_pipeline.py
for the "soft fact" (prose) fields.

WHY THIS SPLIT (justification):
- Price, bedrooms, area, availability, agent names are STRUCTURED, exact-match
  or range-query data. A vector search for "3 bedroom house under 2 crore in
  DHA" is unreliable: embeddings capture semantic similarity, not numeric
  comparison - it might return a 4-bed listing that's *textually* similar
  instead of correctly filtering price < 20,000,000. SQL does this exactly
  and cheaply, with zero hallucination risk on numbers.
- Brochure copy, FAQs, payment-plan fine print, "why this society" style
  content is UNSTRUCTURED prose that varies in wording. There's no fixed
  schema for "reasons to invest in Bahria Town" - that's what embeddings
  and semantic search are for.
- Net effect: the agent NEVER free-generates a price or bedroom count from
  the LLM's world knowledge - those numbers only ever come from a SQL row
  that's echoed back verbatim into the prompt (see generate_answer's
  structured_context in rag_pipeline.py). This is the core anti-hallucination
  mechanism evaluated in hallucination_eval.py.

NOTE (fix): query_properties() and query_commercial() must accept every
keyword argument day3_orchestrator.py's node_retrieve() passes to them.
A previous version of this file dropped `exclude_location` from both
functions and `purpose` from query_commercial while the orchestrator kept
calling them with those kwargs - that mismatch raises a TypeError on
every single sql-routed turn, which is functionally indistinguishable
from "not fetching from the database" unless something upstream silently
swallows the exception. Keep these signatures in lockstep with the
orchestrator's call sites.

NOTE (fix, this pass): prices were being spoken digit-by-digit by the TTS
layer (e.g. "PKR 57,000,000" read out as individual digits) instead of
naturally ("57 lakh", "5.7 crore" - the way the persona itself already
talks in the sample transcripts). format_price_pkr() below converts every
price into Pakistani lakh/crore notation before it ever reaches
format_as_context(), so the LLM only ever sees - and therefore only ever
speaks - the natural form.
"""

import sqlite3
import pandas as pd

DB_PATH = "./realestate.db"
AMENITIES_CSV = "./location_amenities.csv"
FACILITIES_CSV = "./nearby_facilities.csv"

# CONFIRMED real columns from Property_with_Feature_Engineering.csv (191,393 rows, 24 cols):
# property_id, location_id, page_url, property_type, price, price_bin, location, city,
# province_name, locality, latitude, longitude, baths, area, area_marla, area_sqft,
# purpose, bedrooms, date_added, year, month, day, agency, agent
MAX_PLAUSIBLE_BATHS = 20
MIN_PLAUSIBLE_SALE_PRICE = 1_000_000   # PKR - a "For Sale" listing below this is a data error
MIN_PLAUSIBLE_RENT_PRICE = 5_000       # PKR/month - rent floor stays low, small units exist


def format_price_pkr(value):
    """
    Converts a raw PKR number into Pakistani lakh/crore notation for natural
    speech, instead of a comma-grouped digit string that TTS engines tend to
    read digit-by-digit. Matches the register your own transcripts already
    use naturally ("5.7 crore", "17 lakh", "65 lakh").

    1 lakh = 100,000 | 1 crore = 10,000,000

    Examples:
      57,000,000 -> "5 crore 70 lakh"
      6,500,000  -> "65 lakh"
      1,700,000  -> "17 lakh"
      8,500      -> "8,500" (below 1 lakh - too small for lakh notation to help)
      None       -> "price not verified"
    """
    if value is None:
        return "price not verified"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "price not verified"

    CRORE = 10_000_000
    LAKH = 100_000

    if value >= CRORE:
        whole_crore = int(value // CRORE)
        remainder = value - whole_crore * CRORE
        lakh_part = int(round(remainder / LAKH))
        if lakh_part >= 100:  # rounding pushed it into the next crore
            whole_crore += 1
            lakh_part = 0
        return f"{whole_crore} crore {lakh_part} lakh" if lakh_part else f"{whole_crore} crore"

    if value >= LAKH:
        whole_lakh = int(value // LAKH)
        remainder = value - whole_lakh * LAKH
        thousand_part = int(round(remainder / 1_000))
        if thousand_part >= 100:
            whole_lakh += 1
            thousand_part = 0
        return f"{whole_lakh} lakh {thousand_part} thousand" if thousand_part else f"{whole_lakh} lakh"

    return f"{value:,.0f}"


def build_database(zameen_csv_path, commercial_csv_path, db_path=DB_PATH,
                   amenities_csv_path=AMENITIES_CSV,
                   facilities_csv_path=FACILITIES_CSV):
    conn = sqlite3.connect(db_path)

    zameen_df = pd.read_csv(zameen_csv_path)

    if "baths" in zameen_df.columns:
        bad_baths = zameen_df["baths"] > MAX_PLAUSIBLE_BATHS
        if bad_baths.any():
            print(f"Nulling out {bad_baths.sum()} rows with implausible baths values (>{MAX_PLAUSIBLE_BATHS})")
            zameen_df.loc[bad_baths, "baths"] = None

    if "price" in zameen_df.columns and "purpose" in zameen_df.columns:
        sale_mask = zameen_df["purpose"] == "For Sale"
        rent_mask = zameen_df["purpose"] == "For Rent"
        bad_sale_price = sale_mask & (zameen_df["price"] < MIN_PLAUSIBLE_SALE_PRICE)
        bad_rent_price = rent_mask & (zameen_df["price"] < MIN_PLAUSIBLE_RENT_PRICE)
        bad_price = bad_sale_price | bad_rent_price
        if bad_price.any():
            print(
                f"Nulling out {int(bad_price.sum())} rows with implausible price for "
                f"their purpose ({int(bad_sale_price.sum())} sale rows < "
                f"{MIN_PLAUSIBLE_SALE_PRICE:,}, {int(bad_rent_price.sum())} rent rows < "
                f"{MIN_PLAUSIBLE_RENT_PRICE:,})"
            )
            zameen_df.loc[bad_price, "price"] = None
    elif "price" in zameen_df.columns:
        bad_price = zameen_df["price"] < MIN_PLAUSIBLE_RENT_PRICE
        zameen_df.loc[bad_price, "price"] = None

    zameen_df.to_sql("properties", conn, if_exists="replace", index=False)

    commercial_df = pd.read_csv(commercial_csv_path)
    commercial_df.to_sql("commercial_properties", conn, if_exists="replace", index=False)

    pd.read_csv(amenities_csv_path).to_sql(
        "location_amenities", conn, if_exists="replace", index=False
    )
    pd.read_csv(facilities_csv_path).to_sql(
        "nearby_facilities", conn, if_exists="replace", index=False
    )

    conn.execute("CREATE INDEX IF NOT EXISTS idx_prop_city ON properties(city)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_prop_price ON properties(price)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_prop_locality ON properties(locality)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_comm_city ON commercial_properties(city)")
    conn.commit()
    conn.close()
    print(f"Loaded {len(zameen_df)} residential + {len(commercial_df)} commercial rows into {db_path}")


def enrich_listing_rows(rows):
    """Attach verified demo amenities and facilities by city/location."""
    if not rows:
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    enriched = []
    for row in rows:
        item = dict(row)
        city = str(item.get("city") or "")
        location = str(item.get("location") or "")
        amenity = conn.execute(
            """SELECT amenities FROM location_amenities
               WHERE LOWER(city)=LOWER(?) AND LOWER(?) LIKE LOWER(location) || '%'
               ORDER BY LENGTH(location) DESC LIMIT 1""",
            (city, location),
        ).fetchone()
        facility = conn.execute(
            """SELECT school, hospital FROM nearby_facilities
               WHERE LOWER(city)=LOWER(?) AND LOWER(?) LIKE LOWER(location) || '%'
               ORDER BY LENGTH(location) DESC LIMIT 1""",
            (city, location),
        ).fetchone()
        val_price = item.get("price_pkr") if item.get("price_pkr") is not None else item.get("price")
        item["price"] = val_price
        item["price_pkr"] = val_price
        item["amenities"] = amenity["amenities"] if amenity else "Not available in verified data"
        item["nearby_school"] = facility["school"] if facility else "Not available in verified data"
        item["nearby_hospital"] = facility["hospital"] if facility else "Not available in verified data"
        enriched.append(item)
    conn.close()
    return enriched


def query_properties(
    city=None,
    location=None,
    exclude_location=None,
    purpose=None,
    min_price=None,
    max_price=None,
    bedrooms=None,
    property_type=None,
    limit=5,
    db_path=DB_PATH
):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    clauses = []
    params = []

    if city:
        clauses.append("city = ?")
        params.append(city)

    if location:
        clauses.append(
            "(LOWER(location) = ? OR LOWER(location) LIKE ? OR "
            "LOWER(locality) = ? OR LOWER(locality) LIKE ?)"
        )
        location_value = location.lower().strip()
        location_prefix = f"{location_value} %"
        params.extend([location_value, location_prefix, location_value, location_prefix])

    if exclude_location:
        clauses.append(
            "NOT (LOWER(location) = ? OR LOWER(location) LIKE ? OR "
            "LOWER(locality) = ? OR LOWER(locality) LIKE ?)"
        )
        excl_value = exclude_location.lower().strip()
        excl_prefix = f"{excl_value} %"
        params.extend([excl_value, excl_prefix, excl_value, excl_prefix])

    if purpose:
        clauses.append("purpose = ?")
        params.append(purpose)

    if min_price is not None:
        clauses.append("price >= ?")
        params.append(min_price)

    if max_price is not None:
        clauses.append("price <= ?")
        params.append(max_price)

    if bedrooms is not None:
        clauses.append("bedrooms = ?")
        params.append(bedrooms)

    if property_type:
        clauses.append("property_type = ?")
        params.append(property_type)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    sql = f"""
        SELECT *
        FROM properties
        {where}
        ORDER BY date_added DESC
        LIMIT ?
    """
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    return [dict(r) for r in rows]


def query_commercial(city=None, location=None, exclude_location=None, unit_type=None, purpose=None,
                      max_price=None, suitable_for=None, limit=5, db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    clauses, params = [], []

    if city:
        clauses.append("city = ?"); params.append(city)

    if location:
        clauses.append("(LOWER(location) = ? OR LOWER(location) LIKE ?)")
        location_value = location.lower().strip()
        params.extend([location_value, f"{location_value}%"])

    if exclude_location:
        clauses.append("NOT (LOWER(location) = ? OR LOWER(location) LIKE ?)")
        excl_value = exclude_location.lower().strip()
        params.extend([excl_value, f"{excl_value}%"])

    if unit_type:
        clauses.append("unit_type = ?"); params.append(unit_type)
    if purpose:
        clauses.append("purpose = ?"); params.append(purpose)
    if max_price is not None:
        clauses.append("price_pkr <= ?"); params.append(max_price)
    if suitable_for:
        clauses.append("suitable_for LIKE ?"); params.append(f"%{suitable_for}%")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"SELECT * FROM commercial_properties {where} LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def format_as_context(rows, kind="residential"):
    """Turns SQL rows into the exact-facts text block fed to the LLM (see rag_pipeline.generate_answer)."""
    if not rows:
        return "No matching properties found in the database."
    lines = []
    for r in rows:
        if kind == "residential":
            baths_str = r.get("baths") if r.get("baths") is not None else "N/A"
            agent_str = r.get("agent") or "not listed"
            price_str = f"PKR {format_price_pkr(r.get('price'))}"
            lines.append(
                f"- {r.get('property_type')} in {r.get('location')}, {r.get('city')} | "
                f"{price_str} | {r.get('bedrooms')} bed, {baths_str} bath | "
                f"{r.get('area')} ({r.get('area_marla')} marla / {r.get('area_sqft'):,.0f} sqft) | "
                f"Agent: {agent_str} | Amenities: {r.get('amenities', 'not verified')} | "
                f"School: {r.get('nearby_school', 'not verified')} | "
                f"Hospital: {r.get('nearby_hospital', 'not verified')}"
            )
        else:
            price_str = f"PKR {format_price_pkr(r.get('price_pkr'))}"
            lines.append(
                f"- {r.get('unit_type')} in {r.get('location')}, {r.get('city')} | "
                f"{price_str} | {r.get('area_sqft')} sqft | "
                f"Suitable for: {r.get('suitable_for')} | Amenities: {r.get('amenities', 'not verified')} | "
                f"School: {r.get('nearby_school', 'not verified')} | "
                f"Hospital: {r.get('nearby_hospital', 'not verified')}"
            )
    return "\n".join(lines)


if __name__ == "__main__":
    print("Run build_database('path/to/zameen.csv', 'dummy_commercial_properties.csv') "
          "once you upload the Zameen CSV.")