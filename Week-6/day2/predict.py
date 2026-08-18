"""
predict.py — Week 6 / Day 2 — CM-IT
=====================================
Clean, documented callable functions wrapping the two saved model
pipelines. This is the module Day 4 turns into LangChain/LangGraph agent
tools — keep the public functions' signatures and return shapes stable.

Public API
----------
predict_match_winner(home_team, away_team, date=None, venue=None) -> dict
predict_top_player(team=None, opponent=None, venue=None, is_home=None,
                    top_n=5, as_of_date=None) -> list[dict]

Both functions:
  * validate inputs and raise ValueError with a clear message on bad input
    (unknown team, date outside the data range, etc) instead of crashing
    inside sklearn with an opaque error
  * lazily load the saved joblib artifacts on first call and cache them
    module-level, so repeated calls (e.g. from an agent loop) are fast

Quick-start
-----------
    from predict import predict_match_winner, predict_top_player

    predict_match_winner("Richmond Tigers", "Collingwood Magpies")
    # -> {'home_team': 'Richmond Tigers', 'away_team': 'Collingwood Magpies',
    #     'predicted_winner': 'Collingwood Magpies',
    #     'home_win_probability': 0.41, 'away_win_probability': 0.59,
    #     'venue': 'Melbourne Cricket Ground', 'as_of_date': '2025-09-27'}

    predict_top_player(team="Geelong Cats", top_n=5)
    # -> [{'player_id': 43668, 'team': 'Geelong Cats',
    #      'predicted_fantasy_points': 101.2, 'rank': 1}, ...]
"""
from __future__ import annotations

from pathlib import Path
from functools import lru_cache
from datetime import datetime

import numpy as np
import pandas as pd
import joblib

import common as C

PIPELINE_DIR = Path(__file__).resolve().parent / "pipelines"


# ==========================================================================
# Lazy-loaded artifact cache
# ==========================================================================
@lru_cache(maxsize=1)
def _load_match_artifacts():
    pipe = joblib.load(PIPELINE_DIR / "match_winner_pipeline.joblib")
    meta = joblib.load(PIPELINE_DIR / "match_winner_meta.joblib")
    panel = joblib.load(PIPELINE_DIR / "match_history_panel.joblib")
    ranking = joblib.load(PIPELINE_DIR / "team_ranking_table.joblib")
    return pipe, meta, panel, ranking


@lru_cache(maxsize=1)
def _load_player_artifacts():
    pipe = joblib.load(PIPELINE_DIR / "top_player_pipeline.joblib")
    meta = joblib.load(PIPELINE_DIR / "top_player_meta.joblib")
    history = joblib.load(PIPELINE_DIR / "player_history.joblib")
    ranking = joblib.load(PIPELINE_DIR / "team_ranking_table.joblib")
    return pipe, meta, history, ranking


# ==========================================================================
# Shared validation helpers
# ==========================================================================
def _validate_team(team_key: str, known_teams: list[str], role: str) -> str:
    key = C.normalize_team(team_key)
    if key not in known_teams:
        raise ValueError(
            f"Unknown {role} team '{team_key}'. Must be one of the "
            f"{len(known_teams)} teams seen in training data, e.g. "
            f"{sorted(known_teams)[:5]}..."
        )
    return key


def _validate_date(date_str: str | None, min_date: str, max_date: str) -> pd.Timestamp:
    if date_str is None:
        return pd.Timestamp(max_date)
    try:
        ts = pd.Timestamp(date_str)
    except (ValueError, TypeError) as e:
        raise ValueError(f"Could not parse date '{date_str}'. Use 'YYYY-MM-DD'.") from e
    if ts < pd.Timestamp(min_date):
        raise ValueError(
            f"Date {ts.date()} is before the earliest data we have ({min_date}); "
            "no historical form can be computed that far back."
        )
    return ts


# ==========================================================================
# MATCH WINNER
# ==========================================================================
def _team_form_asof(panel: pd.DataFrame, team_key: str, opp_key: str,
                     venue: str, as_of_date: pd.Timestamp) -> dict:
    """Recompute the same rolling/expanding "form" aggregates used in
    training, but on demand for a single team as of an arbitrary date --
    using only rows strictly before as_of_date (no leakage)."""
    hist = panel[(panel["team_key"] == team_key) & (panel["match_date"] < as_of_date)]
    hist = hist.sort_values("match_date")

    if len(hist) == 0:
        form_win_rate_5 = C.DEFAULT_WIN_RATE
        form_avg_score_for_5 = panel["team_score"].mean()
        form_avg_score_against_5 = panel["team_score"].mean()
        form_avg_margin_5 = C.DEFAULT_MARGIN
        career_matches_played = 0
    else:
        last5 = hist.tail(C.ROLLING_WINDOW)
        form_win_rate_5 = last5["win"].mean()
        form_avg_score_for_5 = last5["team_score"].mean()
        form_avg_score_against_5 = last5["opponent_score"].mean()
        form_avg_margin_5 = last5["margin"].mean()
        career_matches_played = len(hist)

    h2h_hist = hist[hist["opp_key"] == opp_key]
    h2h_win_rate = h2h_hist["win"].mean() if len(h2h_hist) else C.DEFAULT_WIN_RATE

    venue_hist = hist[hist["venue"] == venue]
    venue_win_rate = venue_hist["win"].mean() if len(venue_hist) else C.DEFAULT_WIN_RATE

    return dict(
        form_win_rate_5=form_win_rate_5,
        form_avg_score_for_5=form_avg_score_for_5,
        form_avg_score_against_5=form_avg_score_against_5,
        form_avg_margin_5=form_avg_margin_5,
        career_matches_played=career_matches_played,
        h2h_win_rate=h2h_win_rate,
        venue_win_rate=venue_win_rate,
    )


def _infer_home_venue(panel: pd.DataFrame, team_key: str) -> str:
    home_rows = panel[(panel["team_key"] == team_key) & (panel["is_home"] == 1)]
    if len(home_rows) == 0:
        return "UNKNOWN_VENUE"
    return home_rows["venue"].mode().iloc[0]


def predict_match_winner(home_team: str, away_team: str,
                          date: str | None = None, venue: str | None = None) -> dict:
    """Predict the winner of a match between two teams.

    Parameters
    ----------
    home_team, away_team : str
        Team names (case/whitespace-insensitive), e.g. "Richmond Tigers".
    date : str, optional
        'YYYY-MM-DD'. Determines which historical matches count as "form"
        (only matches strictly before this date are used). Defaults to the
        most recent date in the training data (i.e. "using everything we
        know").
    venue : str, optional
        Venue name. Defaults to the home team's most common home ground.

    Returns
    -------
    dict with predicted_winner, home_win_probability, away_win_probability,
    venue, and as_of_date.

    Raises
    ------
    ValueError on an unknown team name or an out-of-range date.
    """
    pipe, meta, panel, ranking = _load_match_artifacts()

    home_key = _validate_team(home_team, meta["known_teams"], "home")
    away_key = _validate_team(away_team, meta["known_teams"], "away")
    if home_key == away_key:
        raise ValueError("home_team and away_team must be different teams.")
    as_of = _validate_date(date, meta["min_date"], meta["max_date"])

    if venue is None:
        venue = _infer_home_venue(panel, home_key)
    elif venue not in meta["known_venues"]:
        raise ValueError(f"Unknown venue '{venue}'. See meta['known_venues'] for valid options.")

    home_form = _team_form_asof(panel, home_key, away_key, venue, as_of)
    away_form = _team_form_asof(panel, away_key, home_key, venue, as_of)

    rank_lookup = ranking.set_index("team_key")
    home_rank = rank_lookup["rank_avg_performance"].get(home_key, ranking["rank_avg_performance"].mean())
    away_rank = rank_lookup["rank_avg_performance"].get(away_key, ranking["rank_avg_performance"].mean())

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
        "venue": venue,
    }
    X = pd.DataFrame([row])[C.MATCH_NUMERIC_FEATURES + C.MATCH_CATEGORICAL_FEATURES]
    proba_home = float(pipe.predict_proba(X)[0, 1])

    winner = C.display_team_name(home_key) if proba_home >= 0.5 else C.display_team_name(away_key)
    return {
        "home_team": C.display_team_name(home_key),
        "away_team": C.display_team_name(away_key),
        "predicted_winner": winner,
        "home_win_probability": round(proba_home, 3),
        "away_win_probability": round(1 - proba_home, 3),
        "venue": venue,
        "as_of_date": str(as_of.date()),
        "model": meta["final_model_name"],
    }


# ==========================================================================
# TOP PLAYER
# ==========================================================================
def predict_top_player(team: str | None = None, opponent: str | None = None,
                        venue: str | None = None, is_home: bool | None = None,
                        top_n: int = 5, as_of_date: str | None = None) -> list[dict]:
    """Rank players by predicted fantasy_points for an upcoming match/round.

    Parameters
    ----------
    team : str, optional
        Restrict to one team's current roster. If None, ranks across every
        team's current roster (league-wide top-N).
    opponent : str, optional
        Opposition team, used for the opponent-strength feature. Ignored if
        `team` is None.
    venue : str, optional
        Venue for the fixture. Defaults to 'UNKNOWN_VENUE' if not given.
    is_home : bool, optional
        Whether `team` is playing at home. Defaults to False if not given.
    top_n : int, default 5
        How many players to return.
    as_of_date : str, optional
        'YYYY-MM-DD'; only players' history strictly before this date is
        used to build their form features. Defaults to the latest date in
        the training data.

    Returns
    -------
    list[dict], each with player_id, team, predicted_fantasy_points, rank.

    Raises
    ------
    ValueError on an unknown team/opponent name, an out-of-range date, or
    top_n < 1.
    """
    pipe, meta, history, ranking = _load_player_artifacts()

    if top_n < 1:
        raise ValueError("top_n must be >= 1")

    as_of = _validate_date(as_of_date, meta["min_date"], meta["max_date"])

    team_key = None
    if team is not None:
        team_key = _validate_team(team, meta["known_teams"], "team")
    opp_key = None
    if opponent is not None:
        opp_key = _validate_team(opponent, meta["known_teams"], "opponent")

    hist = history[history["match_date"] < as_of]
    if team_key is not None:
        hist = hist[hist["team_key"] == team_key]
    if len(hist) == 0:
        raise ValueError(
            f"No historical data available for team='{team}' before {as_of.date()}. "
            "Try an earlier as_of_date is not possible (this IS the earliest); "
            "check the team name or data coverage."
        )

    # current roster snapshot: most recent row per player
    latest = hist.sort_values("match_date").groupby("player_id").tail(1).copy()

    rank_lookup = ranking.set_index("team_key")["rank_avg_performance"]
    league_avg_rank = ranking["rank_avg_performance"].mean()
    latest["team_rank_avg_performance"] = latest["team_key"].map(rank_lookup).fillna(league_avg_rank)
    latest["opp_rank_avg_performance"] = (
        rank_lookup.get(opp_key, league_avg_rank) if opp_key else league_avg_rank
    )
    latest["prior_season_avg_fantasy"] = latest["career_avg_fantasy_to_date"]  # best available proxy
    latest["has_prior_season_data"] = 1
    latest["is_home"] = int(bool(is_home))
    latest["opp_key"] = opp_key if opp_key else "UNKNOWN_OPPONENT"
    latest["venue"] = venue if venue else "UNKNOWN_VENUE"

    X = latest[C.PLAYER_NUMERIC_FEATURES + C.PLAYER_CATEGORICAL_FEATURES]
    latest["predicted_fantasy_points"] = pipe.predict(X)

    top = latest.sort_values("predicted_fantasy_points", ascending=False).head(top_n)
    results = []
    for rank_i, (_, r) in enumerate(top.iterrows(), start=1):
        results.append({
            "player_id": int(r["player_id"]),
            "team": C.display_team_name(r["team_key"]),
            "predicted_fantasy_points": round(float(r["predicted_fantasy_points"]), 1),
            "rank": rank_i,
        })
    return results


if __name__ == "__main__":
    print(predict_match_winner("Richmond Tigers", "Collingwood Magpies"))
    print(predict_match_winner("Geelong Cats", "Hawthorn Hawks", venue="GMHBA Stadium"))
    for row in predict_top_player(team="Geelong Cats", top_n=5):
        print(row)
    for row in predict_top_player(top_n=5):
        print(row)
