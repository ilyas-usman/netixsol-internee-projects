"""
prediction_tools.py — Week 6 / Day 4 — Task 3
================================================
Wraps Day 2's predict_match_winner / predict_top_player as tools the
prediction node can call, adding:
  1. Team-alias resolution (nicknames -> dataset keys) BEFORE hitting
     predict.py, via resolvers.py, so "will the Pies beat the Cats" works.
  2. Date resolution for "this week" / "next round" style phrasing.
  3. A real, non-fabricated top-2/3-feature grounding explanation attached
     to every successful prediction, per Task 3's requirement.

We deliberately do NOT modify predict.py or common.py — Day 2's docstring
says to keep their public signatures/return shapes stable, and everything
needed for grounding is derivable from what's already loaded (the fitted
pipeline + the same as-of-date feature row predict.py itself builds), so
there's no reason to touch the trained-model layer to get it.

--------------------------------------------------------------------------
Design note: date resolution for "this week" / "next round"
--------------------------------------------------------------------------
predict.py's meta['max_date'] is 2025-09-27 — the last date in the
training data, not a live fixture calendar. There is no upcoming-fixtures
file anywhere in the uploaded dataset. So "this week" cannot be resolved
to a real scheduled match date without fabricating one.

Instead: any date-ish phrase that isn't a literal 'YYYY-MM-DD' (this
week, next round, upcoming, now, today, ...) resolves to `date=None`,
which predict.py already defaults to "as of the most recent date we have
data for" — i.e. the prediction uses full available history, and the
response_formatting_node is responsible for stating that plainly ("based
on data through 2025-09-27; no live fixture calendar is available") so
the user isn't misled into thinking this is a scheduled real fixture.
This is a documented scope limitation, not a silent guess.
--------------------------------------------------------------------------
"""
from __future__ import annotations

import re
from typing import Optional

import numpy as np
import pandas as pd

import common as C
import predict as P
from resolvers import resolve_team_for_prediction, is_known_team

_RELATIVE_DATE_PATTERN = re.compile(
    r"\b(this week|next round|next week|upcoming|this round|now|today|current)\b",
    re.IGNORECASE,
)


def resolve_prediction_date(date_hint: Optional[str]) -> Optional[str]:
    """'2025-09-27' passes through unchanged. A relative phrase ('this
    week', 'next round', ...) or nothing at all resolves to None, which
    predict.py treats as 'as of the latest date we have data for'. See
    module docstring for why we don't invent a future fixture date."""
    if not date_hint:
        return None
    if _RELATIVE_DATE_PATTERN.search(date_hint):
        return None
    try:
        pd.Timestamp(date_hint)
        return date_hint
    except (ValueError, TypeError):
        return None  # unparseable -> fall back to "latest available", not a crash


# --------------------------------------------------------------------------
# Match winner: grounding via the model's own global feature_importances_,
# reported alongside the ACTUAL home vs. away values for those features on
# THIS matchup (both real, both traceable to the row predict.py itself
# builds) -- not a fabricated explanation.
# --------------------------------------------------------------------------
def _match_top_features(row: dict, n: int = 3) -> list[str]:
    pipe, meta, panel, ranking = P._load_match_artifacts()
    prep = pipe.named_steps["prep"]
    clf = pipe.named_steps["clf"]

    num_features = C.MATCH_NUMERIC_FEATURES
    cat_names = list(prep.named_transformers_["cat"].get_feature_names_out(C.MATCH_CATEGORICAL_FEATURES))
    all_names = num_features + cat_names
    importances = clf.feature_importances_

    # Rank purely numeric features (categorical/venue one-hot importances
    # are individually tiny and not meaningfully explainable per-team) by
    # global importance, then report each one's actual value for this
    # matchup so the explanation is grounded in real numbers, not just a
    # feature *name*.
    numeric_importance = [
        (name, imp) for name, imp in zip(all_names, importances) if name in num_features
    ]
    numeric_importance.sort(key=lambda x: x[1], reverse=True)

    lines = []
    for name, imp in numeric_importance[:n]:
        val = row.get(name)
        if val is None:
            continue
        if "diff" in name:
            lines.append(f"{name} = {val:+.2f} (positive favors the home team)")
        else:
            lines.append(f"{name} = {val:.2f}")
    return lines


def predict_match_winner_tool(home_team_raw: str, away_team_raw: str,
                               date_hint: Optional[str] = None,
                               venue: Optional[str] = None) -> dict:
    """Task 3 wrapper: resolve aliases + relative date, call predict.py,
    attach a grounded top-feature explanation. Returns a dict with either
    {"ok": True, "result": {...}} or {"ok": False, "error": "..."} — the
    validation node branches on this "ok" flag rather than on exception
    type, so retrieval and prediction failures can be handled uniformly.
    """
    home_key = resolve_team_for_prediction(home_team_raw)
    away_key = resolve_team_for_prediction(away_team_raw)
    resolved_date = resolve_prediction_date(date_hint)

    try:
        result = P.predict_match_winner(home_key, away_key, date=resolved_date, venue=venue)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    # Rebuild the same feature row predict.py used, purely for the
    # explanation -- cheap (all artifacts are already lru_cache'd).
    pipe, meta, panel, ranking = P._load_match_artifacts()
    home_norm = C.normalize_team(home_key)
    away_norm = C.normalize_team(away_key)
    as_of = pd.Timestamp(result["as_of_date"])
    home_form = P._team_form_asof(panel, home_norm, away_norm, result["venue"], as_of)
    away_form = P._team_form_asof(panel, away_norm, home_norm, result["venue"], as_of)
    rank_lookup = ranking.set_index("team_key")["rank_avg_performance"]
    home_rank = rank_lookup.get(home_norm, ranking["rank_avg_performance"].mean())
    away_rank = rank_lookup.get(away_norm, ranking["rank_avg_performance"].mean())
    row = {
        "home_form_win_rate_5": home_form["form_win_rate_5"],
        "home_form_avg_score_for_5": home_form["form_avg_score_for_5"],
        "home_form_avg_score_against_5": home_form["form_avg_score_against_5"],
        "home_form_avg_margin_5": home_form["form_avg_margin_5"],
        "home_career_matches_played": home_form["career_matches_played"],
        "home_h2h_win_rate": home_form["h2h_win_rate"],
        "home_venue_win_rate": home_form["venue_win_rate"],
        "away_form_win_rate_5": away_form["form_win_rate_5"],
        "away_form_avg_score_for_5": away_form["form_avg_score_for_5"],
        "away_form_avg_score_against_5": away_form["form_avg_score_against_5"],
        "away_form_avg_margin_5": away_form["form_avg_margin_5"],
        "away_career_matches_played": away_form["career_matches_played"],
        "away_h2h_win_rate": away_form["h2h_win_rate"],
        "away_venue_win_rate": away_form["venue_win_rate"],
        "home_rank_rank_avg_performance": home_rank,
        "away_rank_rank_avg_performance": away_rank,
        "rank_perf_diff": home_rank - away_rank,
        "form_win_rate_diff": home_form["form_win_rate_5"] - away_form["form_win_rate_5"],
        "form_margin_diff": home_form["form_avg_margin_5"] - away_form["form_avg_margin_5"],
    }
    result["top_features"] = _match_top_features(row)
    result["used_live_fixture_date"] = date_hint is not None and resolved_date is not None
    return {"ok": True, "result": result}


# --------------------------------------------------------------------------
# Top player: Ridge is linear, so the per-player contribution
# (standardized_feature_value * coefficient) is an EXACT decomposition of
# that player's predicted score, not an approximation -- report the top
# contributors for the #1 ranked player specifically.
# --------------------------------------------------------------------------
def _top_player_contributions(pipe, row_df: pd.DataFrame, n: int = 3) -> list[str]:
    prep = pipe.named_steps["prep"]
    reg = pipe.named_steps["reg"]
    if not hasattr(reg, "coef_"):
        return []  # only exact for the linear (Ridge) model

    num_features = C.PLAYER_NUMERIC_FEATURES
    cat_names = list(prep.named_transformers_["cat"].get_feature_names_out(C.PLAYER_CATEGORICAL_FEATURES))
    all_names = num_features + cat_names

    X_transformed = prep.transform(row_df)
    if hasattr(X_transformed, "toarray"):
        X_transformed = X_transformed.toarray()
    contributions = X_transformed[0] * reg.coef_

    # only explain the numeric features -- team/opponent/venue one-hot
    # coefficients are per-category quirks, not generalizable "drivers"
    numeric_contribs = [
        (name, contributions[i]) for i, name in enumerate(all_names) if name in num_features
    ]
    numeric_contribs.sort(key=lambda x: abs(x[1]), reverse=True)

    lines = []
    for name, contrib in numeric_contribs[:n]:
        direction = "pushes prediction up" if contrib > 0 else "pushes prediction down"
        lines.append(f"{name} ({direction}, contribution={contrib:+.2f})")
    return lines


def predict_top_player_tool(team_raw: Optional[str] = None, opponent_raw: Optional[str] = None,
                             venue: Optional[str] = None, is_home: Optional[bool] = None,
                             top_n: int = 5, date_hint: Optional[str] = None) -> dict:
    """Task 3 wrapper around predict_top_player with the same resolve-then-
    call-then-explain pattern as the match winner tool above."""
    team_key = resolve_team_for_prediction(team_raw) if team_raw else None
    opp_key = resolve_team_for_prediction(opponent_raw) if opponent_raw else None
    resolved_date = resolve_prediction_date(date_hint)

    try:
        results = P.predict_top_player(
            team=team_key, opponent=opp_key, venue=venue, is_home=is_home,
            top_n=top_n, as_of_date=resolved_date,
        )
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    # Grounded explanation for the #1 ranked player only (cheap, and the
    # #1 player is what most "who will top-score" questions actually want
    # explained).
    pipe, meta, history, ranking = P._load_player_artifacts()
    top_features = []
    if results:
        as_of = pd.Timestamp(resolved_date) if resolved_date else pd.Timestamp(meta["max_date"])
        hist = history[history["match_date"] < as_of]
        if team_key:
            hist = hist[hist["team_key"] == C.normalize_team(team_key)]
        latest = hist.sort_values("match_date").groupby("player_id").tail(1)
        top_row = latest[latest["player_id"] == results[0]["player_id"]].copy()
        if len(top_row):
            rank_lookup = ranking.set_index("team_key")["rank_avg_performance"]
            league_avg_rank = ranking["rank_avg_performance"].mean()
            top_row["team_rank_avg_performance"] = top_row["team_key"].map(rank_lookup).fillna(league_avg_rank)
            top_row["opp_rank_avg_performance"] = (
                rank_lookup.get(C.normalize_team(opp_key), league_avg_rank) if opp_key else league_avg_rank
            )
            top_row["prior_season_avg_fantasy"] = top_row["career_avg_fantasy_to_date"]
            top_row["has_prior_season_data"] = 1
            top_row["is_home"] = int(bool(is_home))
            top_row["opp_key"] = C.normalize_team(opp_key) if opp_key else "UNKNOWN_OPPONENT"
            top_row["venue"] = venue if venue else "UNKNOWN_VENUE"
            X = top_row[C.PLAYER_NUMERIC_FEATURES + C.PLAYER_CATEGORICAL_FEATURES]
            top_features = _top_player_contributions(pipe, X)

    return {
        "ok": True,
        "result": {
            "predictions": results,
            "top_features_for_rank_1": top_features,
            "used_live_fixture_date": date_hint is not None and resolved_date is not None,
            "as_of_date": resolved_date or meta["max_date"],
        },
    }
