"""
Capstone Task 1/2 — Match-winner prediction model.

Design: a transparent, auditable Elo rating system built from the real
match history in team_matches_home_away_raw (1).csv, rather than a
black-box ML model. Rationale: for a capstone that must explain WHY a
probability is what it is (and must ship a disclaimer distinguishing
"predicted probability" from "certainty"), Elo is the right level of
complexity — every rating change traces back to a specific real match
result, there's no training/serving skew, and the "why" is answerable in
one sentence: "Team A is rated higher because it has beaten stronger
opponents more often, recently."

This intentionally does NOT try to be a state-of-the-art AFL predictor
(no venue effects, no player availability, no travel/rest modeling). It's
a defensible baseline that's honest about its own limitations — see
DISCLAIMER below, which every prediction-bearing response must include
verbatim or in substance (enforced via SYSTEM_PROMPT in agent.py).

Imports the same normalized _matches_df, _normalize_team, and _norm
helpers tools.py already built, so team-name resolution ("Pies" ->
"Collingwood Magpies") is identical and consistent across every tool in
the app — there is exactly one team-name-alias system, not two.
"""

from collections import defaultdict
from datetime import datetime

import pandas as pd
from langchain.tools import tool

from tools import _matches_df, _normalize_team, _norm

DISCLAIMER = (
    "This is a predicted probability based on historical Elo rating "
    "momentum, not a certainty. It does not account for injuries, team "
    "selection, weather, or other on-the-day factors."
)

INITIAL_RATING = 1500.0
K_FACTOR = 20.0


def _dedupe_matches(df: pd.DataFrame) -> list:
    """The real dataset has one row PER TEAM per match, so every match
    appears twice (once from each team's perspective). Feeding both rows
    through the Elo update would double-apply every rating change for the
    same result. Build a canonical, order-independent key per match
    (sorted team-name pair + season + round) and keep only the first row
    seen for each key, sorted chronologically so ratings evolve in the
    correct real-world order."""
    # The real dataset has team_name/opponent columns (one row per team per
    # match); the small sample fallback (team_matches.csv) uses
    # home_team/away_team/home_score/away_score instead, one row per
    # match. Normalize the sample schema into the same team_name/opponent/
    # team_score/opponent_score shape (mirrored into two rows per match,
    # same as the real schema) so every downstream function only ever
    # needs to know one set of column names.
    is_real_schema = "team_name" in df.columns and "opponent" in df.columns
    if df.empty:
        return []
    if not is_real_schema:
        if not {"home_team", "away_team", "home_score", "away_score"}.issubset(df.columns):
            return []
        mirrored = []
        for _, r in df.iterrows():
            base = {"season": r.get("season"), "round": r.get("round")}
            mirrored.append({**base, "team_name": r["home_team"], "opponent": r["away_team"],
                              "team_score": r["home_score"], "opponent_score": r["away_score"]})
            mirrored.append({**base, "team_name": r["away_team"], "opponent": r["home_team"],
                              "team_score": r["away_score"], "opponent_score": r["home_score"]})
        df = pd.DataFrame(mirrored)
        is_real_schema = True  # now normalized into the real shape

    work = df.copy()
    work["_pair_key"] = work.apply(
        lambda r: (
            tuple(sorted([str(r["team_name"]).lower(), str(r["opponent"]).lower()])),
            str(r.get("season", "")),
            str(r.get("round", "")),
        ),
        axis=1,
    )
    # Sort chronologically. match_date is a string like 'YYYY-MM-DD' in the
    # real dataset, which sorts correctly as a plain string; fall back to
    # season/round if match_date isn't present.
    sort_cols = ["match_date"] if "match_date" in work.columns else ["season", "round"]
    work = work.sort_values(sort_cols)

    seen = set()
    unique_rows = []
    for _, r in work.iterrows():
        key = r["_pair_key"]
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(r)
    return unique_rows


def _build_elo_ratings(unique_matches: list) -> dict:
    """Single chronological pass. Standard Elo update, K=20, no home-
    ground advantage term (documented limitation, not modeled). Returns a
    dict of {team_name: current_rating} as of the most recent match in
    the dataset — this is what get_match_prediction uses as "now"."""
    ratings = defaultdict(lambda: INITIAL_RATING)
    for r in unique_matches:
        a, b = r.get("team_name"), r.get("opponent")
        a_score, b_score = r.get("team_score"), r.get("opponent_score")
        if a is None or b is None or a_score is None or b_score is None:
            continue
        try:
            a_score, b_score = float(a_score), float(b_score)
        except (TypeError, ValueError):
            continue
        ra, rb = ratings[a], ratings[b]
        expected_a = 1 / (1 + 10 ** ((rb - ra) / 400))
        if a_score > b_score:
            actual_a = 1.0
        elif a_score < b_score:
            actual_a = 0.0
        else:
            actual_a = 0.5
        ratings[a] = ra + K_FACTOR * (actual_a - expected_a)
        ratings[b] = rb + K_FACTOR * ((1 - actual_a) - (1 - expected_a))
    return dict(ratings)


def _expected_score(rating_a: float, rating_b: float) -> float:
    """Standard Elo expected-score formula: probability team A beats team B."""
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))


# Ratings are built once at import time from the full match history
# currently loaded in tools.py — same lifecycle as the dataframes
# themselves (loaded once per process, not re-read per request).
_UNIQUE_MATCHES = _dedupe_matches(_matches_df)
_CURRENT_RATINGS = _build_elo_ratings(_UNIQUE_MATCHES)


@tool
def get_match_prediction(team_a: str, team_b: str) -> str:
    """Predict the win probability for team_a against team_b, based on
    each team's current Elo rating computed from real historical match
    results in the dataset. Use this whenever the user asks who is
    favored, likely to win, or what the odds/chances are between two AFL
    teams — this is a genuine model output, not a lookup of a real
    scheduled game, and the response always includes a disclaimer that
    this is a predicted probability, not a certainty. Returns NOT_FOUND
    only if a team name cannot be resolved to anything in the dataset at
    all (unrecognized team), not for legitimate predictions between two
    real teams."""
    try:
        a = _normalize_team(team_a)
        b = _normalize_team(team_b)
        if a == b:
            return f"NOT_FOUND: '{team_a}' and '{team_b}' resolve to the same team — no prediction against itself."
        # _normalize_team falls back to returning the normalized input
        # unchanged if nothing matches — check the rating dict itself
        # (case-insensitive) to see if we actually have a real team here.
        rating_keys_lower = {k.lower(): k for k in _CURRENT_RATINGS}
        if a not in rating_keys_lower and a not in {_norm(k) for k in _CURRENT_RATINGS}:
            return f"NOT_FOUND: '{team_a}' doesn't match any team in the dataset."
        if b not in rating_keys_lower and b not in {_norm(k) for k in _CURRENT_RATINGS}:
            return f"NOT_FOUND: '{team_b}' doesn't match any team in the dataset."

        # Resolve back to the exact-cased key used in _CURRENT_RATINGS.
        a_key = rating_keys_lower.get(a, a)
        b_key = rating_keys_lower.get(b, b)
        ra = _CURRENT_RATINGS.get(a_key, INITIAL_RATING)
        rb = _CURRENT_RATINGS.get(b_key, INITIAL_RATING)
        prob_a = _expected_score(ra, rb)
        prob_b = 1 - prob_a

        return (
            f"Predicted win probability — {team_a}: {prob_a:.0%}, "
            f"{team_b}: {prob_b:.0%} "
            f"(Elo ratings: {team_a} {ra:.0f}, {team_b} {rb:.0f}, "
            f"from {len(_UNIQUE_MATCHES)} historical matches on record). "
            f"{DISCLAIMER}"
        )
    except Exception as e:
        return f"ERROR: could not compute a prediction for {team_a} vs {team_b} ({type(e).__name__}: {e})."


def naive_ladder_prediction(team_a_win_pct: float, team_b_win_pct: float) -> str:
    """Baseline benchmark used ONLY in the eval suite (Capstone Task 2),
    never exposed to the agent/user. Predicts the team with the higher
    win percentage so far. Returns 'a', 'b', or 'tie'. This is
    deliberately simpler than Elo (no opponent-strength adjustment) — the
    point is to see how much the more expensive Elo model buys us over
    this trivial baseline, not to build a strong baseline."""
    if team_a_win_pct > team_b_win_pct:
        return "a"
    if team_b_win_pct > team_a_win_pct:
        return "b"
    return "tie"


def backtest_elo_vs_naive() -> dict:
    """Walk-forward backtest (Capstone Task 2's benchmark comparison):
    replays every deduped match in chronological order. Before updating
    ratings/records with a match's result, predicts the winner two ways:
      1. Elo: whichever team's CURRENT (pre-match) rating is higher.
      2. Naive: whichever team's CURRENT (pre-match) season win% is
         higher (ties broken as a coin-flip miss, i.e. scored as
         incorrect, since a naive model with no opinion shouldn't get
         credit).
    Both predictions are checked against the actual result, then ratings
    and win/loss records are updated with that match before moving to the
    next one — so neither model ever sees the future. Returns a dict with
    accuracy for each model and the number of matches evaluated (the
    first several matches of each team's season aren't evaluated for the
    naive model until it has at least one prior game on record, to avoid
    scoring an undefined 0-0 win percentage)."""
    ratings = defaultdict(lambda: INITIAL_RATING)
    season_record = defaultdict(lambda: {"wins": 0, "games": 0})  # keyed by (team, season)

    elo_correct = 0
    naive_correct = 0
    evaluated = 0

    for r in _UNIQUE_MATCHES:
        a, b = r.get("team_name"), r.get("opponent")
        a_score, b_score = r.get("team_score"), r.get("opponent_score")
        season = r.get("season")
        if a is None or b is None or a_score is None or b_score is None:
            continue
        try:
            a_score, b_score = float(a_score), float(b_score)
        except (TypeError, ValueError):
            continue

        rec_a = season_record[(a, season)]
        rec_b = season_record[(b, season)]

        # Only evaluate once both teams have at least one prior game this
        # season, so the naive model has a real win% to compare, not a
        # meaningless 0/0.
        if rec_a["games"] > 0 and rec_b["games"] > 0:
            evaluated += 1
            ra, rb = ratings[a], ratings[b]
            elo_pick = "a" if ra > rb else ("b" if rb > ra else "tie")

            a_pct = rec_a["wins"] / rec_a["games"]
            b_pct = rec_b["wins"] / rec_b["games"]
            naive_pick = naive_ladder_prediction(a_pct, b_pct)

            actual = "a" if a_score > b_score else ("b" if b_score > a_score else "tie")
            if elo_pick == actual:
                elo_correct += 1
            if naive_pick == actual:
                naive_correct += 1

        # Now update ratings and records with this match's real result.
        ra, rb = ratings[a], ratings[b]
        expected_a = _expected_score(ra, rb)
        actual_a = 1.0 if a_score > b_score else (0.0 if a_score < b_score else 0.5)
        ratings[a] = ra + K_FACTOR * (actual_a - expected_a)
        ratings[b] = rb + K_FACTOR * ((1 - actual_a) - (1 - expected_a))

        rec_a["games"] += 1
        rec_b["games"] += 1
        if a_score > b_score:
            rec_a["wins"] += 1
        elif b_score > a_score:
            rec_b["wins"] += 1

    return {
        "matches_evaluated": evaluated,
        "elo_accuracy": elo_correct / evaluated if evaluated else None,
        "naive_accuracy": naive_correct / evaluated if evaluated else None,
        "elo_correct": elo_correct,
        "naive_correct": naive_correct,
    }


PREDICTION_TOOLS = [get_match_prediction]
