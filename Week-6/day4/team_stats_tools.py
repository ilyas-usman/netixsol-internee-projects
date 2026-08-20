"""
team_stats_tools.py — Week 6 / Day 4 (extension, added post-submission)
==========================================================================
Day 3's tools.py has 7 retrieval tools, all either player-level or
team-vs-team head-to-head (get_team_head_to_head compares exactly two
NAMED teams). None of them answer a league-wide ranking question like
"which team had the best win rate in 2023" or "...across 2022 and 2023"
-- that surfaced as a live bug during interactive testing: the router
mapped these to get_season_leader (a player-stat leaderboard) which
correctly-but-confusingly reported "'win rate' is not a tracked stat
column," because win rate isn't a per-player number at all.

This tool closes that gap using data that's already loaded elsewhere
(team_matches_home_away_raw.csv, via common.py's load_matches so team-key
normalization stays identical to every other tool in the system) --
no new dataset file needed.
"""
from __future__ import annotations

from pathlib import Path
from functools import lru_cache
from typing import Optional

import pandas as pd
from langchain_core.tools import tool

import common as C

DATA_DIR = Path(__file__).resolve().parent / "dataset"


@lru_cache(maxsize=1)
def _load_team_matches() -> pd.DataFrame:
    return C.load_matches(DATA_DIR)


@tool
def get_team_win_rate_leader(season_start: int, season_end: Optional[int] = None, top_n: int = 5) -> str:
    """Rank AFL teams by win rate (wins / games played) for one season or a
    season range (inclusive). Use for league-wide standings questions like
    'which team had the best win rate in 2023' or 'best win rate across
    2022 and 2023' -- NOT for comparing two specific named teams (that's
    get_team_head_to_head instead).

    Args:
        season_start: first season year to include, e.g. 2022.
        season_end: last season year to include, inclusive. Omit for a
            single-season query (defaults to season_start).
        top_n: how many teams to return, best win rate first.
    """
    season_end = season_end or season_start
    if season_end < season_start:
        season_start, season_end = season_end, season_start

    matches = _load_team_matches()
    subset = matches[(matches["year"] >= season_start) & (matches["year"] <= season_end)].copy()
    if subset.empty:
        return f"NOT_FOUND: no matches on record for {season_start}-{season_end}."

    subset["win"] = (subset["result"] == "W").astype(int)
    subset["played"] = 1
    agg = subset.groupby("team_key", as_index=False).agg(
        wins=("win", "sum"), games=("played", "sum")
    )
    agg["win_rate"] = agg["wins"] / agg["games"]
    agg = agg.sort_values("win_rate", ascending=False).head(top_n)

    label = str(season_start) if season_start == season_end else f"{season_start}-{season_end}"
    total_teams = matches["team_key"].nunique()
    lines = [f"Best win rate, {label} (top {len(agg)} of {total_teams} teams):"]
    for i, (_, r) in enumerate(agg.iterrows(), start=1):
        lines.append(
            f"{i}. {C.display_team_name(r['team_key'])} — {r['win_rate']:.1%} "
            f"({int(r['wins'])}/{int(r['games'])} wins)"
        )
    return "\n".join(lines)