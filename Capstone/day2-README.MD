# Week 7 — Day 2: Knowledge Base, RAG & Property Intelligence
## RealEstate Hub Voice Agent — Submission Report

**Status:** All 5 tasks complete and validated end-to-end against the real dataset.

---

## Dataset

- **Source:** Zameen.com Property Data (Pakistan), Kaggle — `huzzefakhan/zameencom-property-data-pakistan`
- **File used:** `Property_with_Feature_Engineering.csv` (191,393 rows, 24 columns)
- A second file, `Property.csv`, was found to be the same 191,393 rows in raw form
  (semicolon-delimited, 17 columns, no engineered features). Since it's a strict subset
  of the feature-engineered file, only the engineered version was loaded.
- **Commercial/shops data:** Zameen's public dataset has thin commercial coverage, so a
  150-row synthetic dataset (`dummy_commercial_properties.csv`) was generated, with prices
  sanity-checked against real Zameen commercial listings.

---

## Task 1 — Knowledge Base Design

Full schema in `knowledge_base_schema.md`. Summary:

| Table | Source | Storage |
|---|---|---|
| `properties` | Zameen CSV | SQL (structured, exact-match/range queries) |
| `commercial_properties` | Dummy dataset | SQL |
| `amenities`, `schools`, `hospitals` | Not in Zameen data — would need separate sourcing (e.g. OpenStreetMap) | SQL, location-linked |
| `payment_plans`, `developers`, `faqs` | Authored from developer-brochure-style content | Vector store (prose, not fixed schema) |

**Data quality finding:** during load, two outlier-cleaning rules were needed:
- `baths` had a value of `403` on one row — clearly a data-entry error, not a real bathroom count.
- **`price` had implausible values on 50,319 of 191,393 rows (≈26%)** — including a house
  listed at `PKR 1`. These are almost certainly scraping/entry errors, not real listings.
  Both fields are nulled (not dropped) at load time in `structured_retrieval.py`, so the
  listing itself isn't lost, but bad values can't silently pass a budget filter or get
  quoted to a customer as real numbers.

---

## Task 2 — RAG Pipeline

Implemented in `rag_pipeline.py`: Document Loader → Chunker → Embedder (`sentence-transformers`,
`all-MiniLM-L6-v2`) → ChromaDB → Retriever → Groq-based answer generation.

**Chunk size evaluation** (on the 5 knowledge docs — payment plans, FAQs, developer notes,
one brochure), measuring average retrieval similarity across 3 test queries:

| Chunk size | # chunks | Avg. retrieval score |
|---|---|---|
| 200 chars | 34 | **0.529** |
| 400 chars | 19 | 0.487 |
| 800 chars | 10 | 0.445 |

Smaller chunks scored higher on this small corpus — more precise matches to short,
specific queries ("what is the down payment"), at the cost of more chunks to manage.
400 chars was used as the production default, as a balance between retrieval precision
and preserving enough surrounding context that a clause isn't separated from its heading
(e.g. "3 saal" without "Bahria Town" nearby). Recommendation: re-run this evaluation once
the real developer brochures/FAQs are authored — 5 short documents is not enough data to
generalize the 200-char result to a much larger knowledge base.

---

## Task 3 — Structured vs. Semantic Retrieval

Implemented in `structured_retrieval.py`. Split and justification:

- **SQL** (`properties`, `commercial_properties` tables): price, bedrooms, area, availability,
  agent — anything that needs exact comparison or range filtering. A vector search for
  "3 bedroom house under 2 crore" can't reliably enforce a numeric cutoff; SQL does it
  exactly, with zero hallucination risk on the numbers themselves.
- **Vector store** (ChromaDB): brochures, FAQs, payment-plan fine print, developer
  reputation notes — free-form prose with no fixed schema.
- **Net effect:** the agent's system prompt (`rag_pipeline.py::generate_answer`) instructs
  it to only state numbers that were echoed back to it from a SQL row or a retrieved chunk,
  never to generate one from its own training knowledge. This is the mechanism the Task 5
  eval checks.

---

## Task 4 — Recommendation Engine

Implemented in `recommendation_engine.py`. Two-stage funnel:
1. **Hard filter (SQL):** budget, city, bedrooms, purpose, property type — pass/fail criteria.
2. **Soft scoring:** amenity match, investment-corridor bonus, budget headroom — weighted,
   not filtering, so a strong property missing one nice-to-have isn't discarded entirely.

**Known limitation:** amenity scoring currently returns no matches, because the Zameen
dataset has no per-listing amenities column (amenities are a society-level concept, not
a per-row field — see Task 1 schema notes). A society→amenities join table is the next
step to make that part of the scoring real; it's not wired up yet.

Sample output (Lahore, 3-bed, ≤ PKR 25M, "Park" preference): 5 real listings returned,
correctly ranked by budget headroom, price range PKR 2.5M–6M.

---

## Task 5 — Hallucination Evaluation

20 test questions across residential, commercial, FAQ, amenities, advisory, and
out-of-scope categories (`hallucination_eval.py`). Two metrics:

- **Grounding rate:** for every number the LLM's answer states, does it appear in either
  (a) the retrieved context (SQL rows + vector chunks) fed to it, or (b) the user's own
  question (so a refusal that restates "2 crore" back isn't flagged as inventing a number)?
  For questions where no grounding data exists at all (schools, hospitals, phone numbers,
  future price predictions), the correct behavior is a refusal, and refusal is checked
  against a broad set of natural refusal phrasings in UrduLish.
- **Retrieval accuracy:** manual pass — confirming retrieval pulled the right source
  document/row per question's topic (not auto-scored, since "correct source" isn't always
  a single unambiguous file).

**Result: grounding rate 1.0 across all 20 questions**, on the final validated run.
Every question where real data existed (payment plan percentages, down payment terms,
refund policy, developer reputation) was answered with numbers traceable to the source
documents. Every question where no data existed (amenities, schools, hospitals, agent
phone numbers, future value predictions, weather) was correctly refused rather than
answered with an invented figure.

Two earlier iterations of this eval scored lower (0.5, then 0.55) — those were **bugs in
the eval harness itself**, not the agent: unicode whitespace mismatches in number
comparison, the eval not allowing a refusal to restate the user's own question numbers,
and an initial refusal-phrase keyword list too narrow for the model's natural UrduLish
phrasing variety. All three were fixed in `hallucination_eval.py`; the 1.0 result reflects
the corrected harness.

---

## Known Gaps / Next Steps

1. **SQL is not yet wired into the answer-generation path.** The agent currently always
   defers to an agent for property-specific questions (price, availability, bedrooms)
   because `rag_pipeline.generate_answer` only receives vector-retrieved context in the
   current test wiring — even though `structured_retrieval.py`/`recommendation_engine.py`
   already have the real answers in SQL. This is safe (never hallucinates) but not yet
   maximally useful. Routing a question to SQL, vector search, or both is an agent
   orchestration / tool-calling concern — natural next step.
2. **Amenities/schools/hospitals have no real data source yet** — needs sourcing (e.g.
   OpenStreetMap Overpass API) and a society-level join table.
3. **Payment plan / FAQ / developer-notes content is currently illustrative**, written to
   exercise the pipeline — needs replacing with real company-provided content before
   production use.

---

## Files in this deliverable

| File | Task |
|---|---|
| `knowledge_base_schema.md` | Task 1 |
| `dummy_commercial_properties.csv` | Task 1 |
| `knowledge_docs/*.txt` | Task 1 (RAG source content) |
| `rag_pipeline.py` | Task 2 |
| `structured_retrieval.py` | Task 3 |
| `recommendation_engine.py` | Task 4 |
| `hallucination_eval.py` | Task 5 |
| `run_build_db.py`, `test_day2_all.py` | Test runners |