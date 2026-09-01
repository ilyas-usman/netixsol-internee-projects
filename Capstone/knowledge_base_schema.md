# Week 7 — Day 2 — Task 1: Knowledge Base Design
## RealEstate Hub Voice Agent — Data Model

Source data: Zameen.com Property Data (Pakistan) — Kaggle, `huzzefakhan/zameencom-property-data-pakistan`
(residential + plots), plus a **dummy commercial/shops dataset** created to fill the gap Zameen's
public dump doesn't cover well.

The known Zameen.com Kaggle columns are:
`property_id, location_id, page_url, property_type, price, location, city, province_name,
latitude, longitude, baths, area, purpose, bedrooms, date_added, agency, agent, Area Type,
Area Size, Area Category`

> ⚠️ These are the *documented* columns for that Kaggle dataset. Once you upload your actual CSV
> I'll confirm the real headers and adjust the loaders — dataset re-exports occasionally rename
> or drop columns (e.g. some versions split `date_added` into `date_added` + `agent_added`).

---

## 1. `properties` (core table — from Zameen CSV, cleaned)

| Column | Type | Notes |
|---|---|---|
| property_id | INT PK | from Zameen `property_id` |
| property_type | TEXT | House / Flat / Plot / Room, etc. |
| purpose | TEXT | For Sale / For Rent |
| price | FLOAT | PKR, cleaned (Zameen stores as raw int) |
| price_per_marla | FLOAT | derived: price / (area_marla) — computed at load time |
| bedrooms | INT | nullable for plots |
| baths | INT | nullable for plots |
| area_size | FLOAT | numeric magnitude |
| area_unit | TEXT | Marla / Kanal / Sq. Ft (from `Area Type`) |
| area_sqft | FLOAT | derived: normalized to sqft for cross-comparison |
| city | TEXT | e.g. Lahore, Karachi, Islamabad |
| location | TEXT | society/phase/sector-level, raw Zameen `location` |
| province_name | TEXT | |
| latitude / longitude | FLOAT | for map + distance queries |
| agency | TEXT | |
| agent | TEXT | |
| date_added | DATE | for "recently listed" filtering / freshness |
| listing_status | TEXT | active / sold / rented — maintained internally, not in Zameen data |

## 2. `commercial_properties` (dummy dataset — shops/offices, Task 1 scope note: Zameen commercial coverage is thin)

Columns mirror `properties` plus: `unit_type` (Shop/Office/Plaza Floor/Warehouse),
`floor_number`, `frontage_ft`, `footfall_rating` (Low/Med/High), `suitable_for`
(Retail/F&B/Clinic/Office/Warehouse — multi-value), `monthly_maintenance_pkr`.
~150 synthetic rows across Lahore/Karachi/Islamabad, price ranges sanity-checked against
real Zameen commercial listings so recommendations don't look absurd.

## 3. `amenities` (many-to-many with properties/societies)
`amenity_id, name (Park, Mosque, Gym, Pool, Security, Power Backup, Gated Community, ...),
category (Lifestyle/Security/Utility)` — junction table `property_amenities(property_id, amenity_id)`.
Populated at the **society/location level** (Zameen doesn't give per-listing amenities reliably),
looked up by `location` string.

## 4. `schools` / `hospitals` (location-linked, semantic + geo)
`id, name, type (School/Hospital), category (e.g. O-Level, Govt Hospital, Private Clinic),
city, area/location, latitude, longitude, distance_source (manual/OSM)`.
Not in Zameen data at all — sourced separately (OpenStreetMap Overpass API is the practical
free option, or manually curated per major society for the MVP).

## 5. `payment_plans` (developer-financed properties — plots/new projects)
`plan_id, property_id (nullable, links to a project not a single listing), down_payment_pct,
installment_years, monthly_installment_pkr, possession_charges, notes`.
Sourced from developer brochures (PDF) → this is why it lives in the **vector store**, not SQL:
plans are described in prose ("20% down, 3-year quarterly installments...") not clean numbers.

## 6. `developers`
`developer_id, name, reputation_notes, active_projects (list), contact_info, verified (bool)`.

## 7. `faqs`
`faq_id, question, answer, category (Booking/Payment/Legal/Process), source_doc`.
Free-text — vector store.

---

## Why this split (ties to Task 3)
Numeric/filterable fields that change per-listing and support exact comparisons
(`price`, `bedrooms`, `area_size`, `agent`) go in **SQL tables**. Prose that describes,
persuades, or explains (brochures, FAQs, payment-plan fine print, developer reputation)
goes in the **vector store**. See `structured_retrieval.py` for the router logic and full
justification.
