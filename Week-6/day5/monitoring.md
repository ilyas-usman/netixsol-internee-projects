# AFL Chat Agent — Monitoring & Maintenance Plan

One page. Covers what to track, alert thresholds, re-evaluation cadence,
and the weekly retraining/refresh loop for the match-prediction model.

## What to track

| Metric | Source | Why it matters |
|---|---|---|
| **Response latency** (p50/p95/p99) | `latency_ms` field in `logs/requests.jsonl`, written by `api.py` for every request | Catches a slow model provider, a stuck tool call, or dataset growth degrading pandas filter performance before users complain |
| **Tool error rate** | Grep `logs/requests.jsonl` for `"error": <non-null>` — every tool already wraps its body in try/except and returns an `ERROR:`-prefixed string rather than raising, so tool-level failures are visible in the answer text too (`grep '"error"' logs/requests.jsonl \| wc -l`) | A rising error rate usually means a dataset schema change (a CSV re-export with renamed columns) broke a tool silently |
| **Off-topic leak rate** | `declined` field in the log (heuristic phrase match on the answer) — track the inverse: turns that were NOT declined but arguably should have been requires periodic human spot-check of a sample, since this can't be fully automated | Directly measures whether `SYSTEM_PROMPT`'s scope boundary is holding under new/creative phrasing over time, not just at launch |
| **Grounding flag rate** | `grounded` / `unverified_numbers` fields in the log | A rising rate signals either a new question pattern the checker doesn't handle (like Findings A–D found during development) or the model starting to state ungrounded numbers more often — both need investigation |
| **Rate-limit rejections (429s)** | Count of `HTTPException(429)` responses — add a counter in `api.py` if volume grows beyond what's log-greppable | Distinguishes real traffic growth from abuse/scripted probing |
| **Prediction accuracy drift** | Re-run `backtest_elo_vs_naive()` from `eval_suite.py` against the dataset as new rounds are added | The whole point of Elo is that it's *supposed* to update every round — this isn't drift to panic about, it's the model working. What to actually watch: whether Elo's accuracy edge over the naive baseline (the `diff` printed by `eval_suite.py`) shrinks toward zero or goes negative, which would mean the extra complexity of Elo isn't earning its keep anymore |
| **Token usage estimate** | `est_tokens_in` / `est_tokens_out` in the log (chars/4 estimate — swap for a real tokenizer if a cost budget depends on precision) | Cost tracking and a proxy for unusually long/rambling responses |

## Alert thresholds (starting points — tune after 2–4 weeks of real traffic)

| Alert | Threshold | Action |
|---|---|---|
| Latency p95 | > 8 seconds | Check Groq status page / rate-limit backoff frequency; consider increasing `timeout_seconds` in `agent.py`'s `ask()` only if it's a genuine slow-but-succeeding pattern, not a stuck one |
| Tool error rate | > 5% of requests in a rolling 1-hour window | Check for a dataset schema change or a corrupted CSV re-export |
| Off-topic leak (spot-checked) | Any confirmed leak in a 50-response manual sample | Add the leaking prompt pattern as a new adversarial test case (same process as Findings A–D / Pattern 1–8 in `guardrail-Report.md`), patch `SYSTEM_PROMPT`, re-verify |
| Grounding flag rate | > 2% of requests in a rolling 24-hour window | Sample the flagged transcripts; if it's a new false-positive pattern (like the "?"-detection or accumulated-input fixes already made), patch `verify_grounding()`; if it's a genuine new hallucination pattern, tighten `SYSTEM_PROMPT` rule 1/7/8 |
| Rate-limit rejections | > 50 in an hour from a single `conversation_id` or IP | Likely abuse/scripted probing — consider a temporary IP-level block in front of the API (nginx/Cloudflare), not just the in-memory limiter |
| Elo vs naive accuracy gap | Drops below +5 percentage points over a rolling 8-week backtest | Re-evaluate whether Elo's home-ground-advantage/K-factor assumptions still hold, or whether a stronger model is warranted |

## Re-evaluation cadence

- **Daily**: automated check of latency p95, tool error rate, grounding flag rate (a simple cron job that greps `logs/requests.jsonl` and posts a summary — no dashboard needed to start).
- **Weekly**: re-run `eval_suite.py` in full against the current dataset and current `SYSTEM_PROMPT`/tools — this is the full 25+ case regression suite, not just the automated log metrics, and it catches drift the logs alone can't (e.g. a subtly worse answer that's still "grounded" and "not declined").
- **After every new round of real matches**: re-run `backtest_elo_vs_naive()` and record the accuracy gap in a running log (a simple CSV: `date, matches_evaluated, elo_accuracy, naive_accuracy`) so the trend is visible, not just the latest number.
- **Monthly**: manual spot-check of 20–30 real conversation transcripts from `logs/requests.jsonl` for off-topic leaks and subtle hallucinations the automated checks can't catch (wrong player attributed to a correct number, etc. — the known limitation documented in `guardrail-Report.md`'s Task 3 section).

## Weekly retraining/refresh loop

The Elo model isn't "trained" in the ML sense — it's a deterministic function of match history, recomputed at process startup (`predict.py`, module load time). The "retraining" loop is really a **data refresh + recompute** loop:

1. **New round completes** → the real match-results CSV (`team_matches_home_away_raw (1).csv`, or whatever your pipeline re-exports it as) gets updated with the new round's rows, following whatever process currently produces `final_enriched_dataset.csv` and the team-matches file (this capstone doesn't change your existing data pipeline, only consumes its output).
2. **Dataset refresh** → the updated CSVs are dropped into `dataset/` (or wherever `AFL_DATA_DIR` points), replacing the stale files.
3. **Process restart** → `tools.py` and `predict.py` both load their dataframes and compute Elo ratings once at import time — restarting the API process (`uvicorn api:app`) is what picks up the new data. No code change needed for a routine data refresh.
4. **Re-run `eval_suite.py`** → confirms nothing broke (new team names, new column values, a bye round, etc.) and records the fresh `backtest_elo_vs_naive()` numbers.
5. **Commit the backtest result** to the running accuracy-trend log (see "After every new round" above).

This is a genuinely weekly cadence in practice, since AFL plays roughly one round per week during the season — the loop is intentionally this simple (file replace + restart) rather than a scheduled ML training job, because Elo doesn't benefit from anything more complex than "replay history in order," and adding a training pipeline for a model this simple would be solving a problem that doesn't exist yet. If a future iteration moves to a heavier model (logistic regression on engineered features, gradient boosting, etc.), THIS is the point where a real train/validate/deploy pipeline with versioned model artifacts becomes worth the complexity — not before.

## Known gaps in this monitoring setup (be upfront about them)

- The in-memory rate limiter (`api.py`) resets on every process restart and doesn't share state across multiple API instances — fine for a single-instance demo/capstone deployment, not for a horizontally-scaled production one (would need Redis or a gateway-level limiter).
- `logs/requests.jsonl` is a flat file with no rotation — add `logrotate` or switch to a real log shipper before this runs unattended for weeks.
- The "off-topic leak rate" detection is a keyword heuristic (`_looks_declined` in `api.py`), not a classifier — it will miss creatively-phrased declines and can't be fully trusted without the monthly manual spot-check above.
