"""
common.py
=========
Shared data-loading and feature-engineering logic for the Week-6 Day-2 AFL
prediction models (match winner + top player).

This module is imported by BOTH the training notebook/script and predict.py,
so that inference-time features are computed with the *exact* same logic
that produced the training features. That is the single most common source
of silent train/serve skew, so we centralise it here on purpose.

All "form" features are computed with a strict as-of-date cutoff: a match on
date D only ever uses information strictly before D. This is enforced two
ways:
  * in bulk (training) via groupby().shift(1) / rolling(...).shift(1)
  * at inference (single prediction) via explicit `date <` filtering

Both paths share the same aggregation definitions, so they agree by
construction.
"""
from __future__ import annotations

import re
from pathlib import Path
from dataclasses import dataclass

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# League-wide fallback constants used whenever a team/player has no history
# yet (first-ever match in the dataset, first career game, etc). Using
# neutral, documented defaults instead of silently dropping rows keeps
# every match/player in the training set instead of biasing it toward
# well-established teams/players only.
# --------------------------------------------------------------------------
DEFAULT_WIN_RATE = 0.5
DEFAULT_MARGIN = 0.0
LEAGUE_MEDIAN_FANTASY = 64.0  # from EDA on afl_players_round_by_round_stats_raw

ROLLING_WINDOW = 5  # "recent form" window, in matches, for both models

TEAM_ALIASES = {
    "W. BULLDOGS": "WESTERN BULLDOGS",
}


# --------------------------------------------------------------------------
# Team-name normalisation
# --------------------------------------------------------------------------
def normalize_team(name: str) -> str:
    """Collapse whitespace/tabs/case variants and known abbreviations into
    one canonical UPPERCASE key. The raw CSVs contain the same team spelled
    with leading tabs, leading/trailing spaces, mixed case, and (for the
    Western Bulldogs) an abbreviated form -- all four appear in this
    dataset and must be unified before any join or groupby."""
    if pd.isna(name):
        return name
    s = str(name).replace("\t", " ").strip()
    s = re.sub(r"\s+", " ", s)
    up = s.upper()
    return TEAM_ALIASES.get(up, up)


def display_team_name(name: str) -> str:
    """Title-case a normalized key back into a readable display name."""
    return normalize_team(name).title().replace("Afl", "AFL")


# --------------------------------------------------------------------------
# Raw loaders
# --------------------------------------------------------------------------
def load_matches(data_dir: Path) -> pd.DataFrame:
    df = pd.read_csv(data_dir / "team_matches_home_away_raw.csv", parse_dates=["match_date"])
    df["team_key"] = df["team_name"].map(normalize_team)
    df["opp_key"] = df["opponent"].map(normalize_team)
    df["venue"] = df["venue"].fillna("UNKNOWN_VENUE").str.strip()
    return df


def load_team_ranking(data_dir: Path) -> pd.DataFrame:
    """The team_ranking.csv is a *static*, non-time-resolved aggregate --
    the same team appears many times under different casing/whitespace with
    slightly different values each time (data-quality issue, flagged in the
    notebook's sanity-check section). We normalise the name and average the
    duplicates into a single 'historical strength' score per team. Because
    it is not date-resolved, it is a coarse/leaky-ish prior and is used only
    as a weak supplementary feature -- never as the sole signal."""
    df = pd.read_csv(data_dir / "team_ranking.csv")
    df["team_key"] = df["team"].map(normalize_team)
    agg = df.groupby("team_key", as_index=False).agg(
        rank_avg_performance=("Avg_Performance", "mean"),
        rank_avg_fantasy=("Avg_Fantasy", "mean"),
        rank_avg_goals=("Avg_Goals", "mean"),
        rank_avg_disposals=("Avg_Disposals", "mean"),
    )
    return agg


def load_round_by_round(data_dir: Path) -> pd.DataFrame:
    df = pd.read_csv(data_dir / "afl_players_round_by_round_stats_raw.csv", parse_dates=["match_date"])
    df["team_key"] = df["team"].map(normalize_team)
    df["opp_key"] = df["opponent"].map(normalize_team)
    return df


def load_seasonal(data_dir: Path) -> pd.DataFrame:
    df = pd.read_csv(data_dir / "afl_players_seasonal_stats_raw.csv")
    # season file has both is_finals True/False rows per player/year -> collapse to one
    # whole-of-year average per player, weighted by games played.
    df["games_played"] = pd.to_numeric(df["games_played"], errors="coerce").fillna(0)
    df["avg_fantasy_points"] = pd.to_numeric(df["avg_fantasy_points"], errors="coerce")
    grp = df.groupby(["player_id", "year"], as_index=False).apply(
        lambda g: pd.Series({
            "season_avg_fantasy": np.average(
                g["avg_fantasy_points"].fillna(LEAGUE_MEDIAN_FANTASY),
                weights=g["games_played"].clip(lower=1e-6),
            )
        }),
        include_groups=False,
    )
    return grp


# --------------------------------------------------------------------------
# MATCH WINNER: team-match long panel + rolling "form" features
# --------------------------------------------------------------------------
def build_team_match_panel(matches: pd.DataFrame) -> pd.DataFrame:
    """One row per team per match (so every match contributes two rows:
    the home team's row and the away team's row). This long format is what
    rolling/expanding "recent form" features are computed on."""
    panel = matches[[
        "match_date", "year", "round", "team_key", "opp_key", "home_away",
        "team_score", "opponent_score", "result", "margin", "venue", "crowd",
    ]].copy()
    panel["is_home"] = (panel["home_away"] == "H").astype(int)
    panel["win"] = (panel["result"] == "W").astype(int)
    panel["is_draw"] = (panel["result"] == "D").astype(int)
    panel = panel.sort_values(["team_key", "match_date"]).reset_index(drop=True)
    return panel


def add_rolling_form(panel: pd.DataFrame, window: int = ROLLING_WINDOW) -> pd.DataFrame:
    """Adds strictly-past rolling/expanding features per team, via
    groupby().shift(1) so the current row's own result never leaks into
    its own features."""
    panel = panel.sort_values(["team_key", "match_date"]).copy()
    g = panel.groupby("team_key", group_keys=False)

    panel["form_win_rate_5"] = g["win"].transform(
        lambda s: s.rolling(window, min_periods=1).mean().shift(1)
    )
    panel["form_avg_score_for_5"] = g["team_score"].transform(
        lambda s: s.rolling(window, min_periods=1).mean().shift(1)
    )
    panel["form_avg_score_against_5"] = g["opponent_score"].transform(
        lambda s: s.rolling(window, min_periods=1).mean().shift(1)
    )
    panel["form_avg_margin_5"] = g["margin"].transform(
        lambda s: s.rolling(window, min_periods=1).mean().shift(1)
    )
    panel["career_matches_played"] = g.cumcount()

    # head-to-head win rate vs this specific opponent, prior matches only
    panel = panel.sort_values(["team_key", "opp_key", "match_date"])
    g2 = panel.groupby(["team_key", "opp_key"], group_keys=False)
    panel["h2h_win_rate"] = g2["win"].transform(
        lambda s: s.expanding().mean().shift(1)
    )

    # this team's historical win rate at this venue, prior matches only
    panel = panel.sort_values(["team_key", "venue", "match_date"])
    g3 = panel.groupby(["team_key", "venue"], group_keys=False)
    panel["venue_win_rate"] = g3["win"].transform(
        lambda s: s.expanding().mean().shift(1)
    )

    panel = panel.sort_values(["match_date", "team_key"]).reset_index(drop=True)

    # fill "no history yet" rows with neutral league-average defaults
    panel["form_win_rate_5"] = panel["form_win_rate_5"].fillna(DEFAULT_WIN_RATE)
    panel["form_avg_margin_5"] = panel["form_avg_margin_5"].fillna(DEFAULT_MARGIN)
    league_avg_score = panel["team_score"].mean()
    panel["form_avg_score_for_5"] = panel["form_avg_score_for_5"].fillna(league_avg_score)
    panel["form_avg_score_against_5"] = panel["form_avg_score_against_5"].fillna(league_avg_score)
    panel["h2h_win_rate"] = panel["h2h_win_rate"].fillna(DEFAULT_WIN_RATE)
    panel["venue_win_rate"] = panel["venue_win_rate"].fillna(DEFAULT_WIN_RATE)
    return panel


def build_match_table(matches: pd.DataFrame, panel_with_form: pd.DataFrame,
                       ranking: pd.DataFrame) -> pd.DataFrame:
    """Match-level table (one row per match) with home_*/away_* features
    joined in from the pre-computed rolling panel, plus the static team
    ranking prior. This is the table the match-winner model trains on."""
    home_rows = matches[matches["home_away"] == "H"].copy()
    home_rows = home_rows.rename(columns={
        "team_key": "home_key", "opp_key": "away_key",
        "team_score": "home_score", "opponent_score": "away_score",
        "result": "home_result",
    })

    form_cols = ["form_win_rate_5", "form_avg_score_for_5", "form_avg_score_against_5",
                 "form_avg_margin_5", "career_matches_played", "h2h_win_rate", "venue_win_rate"]

    home_form = panel_with_form[panel_with_form["is_home"] == 1][
        ["match_date", "team_key", "venue"] + form_cols
    ].rename(columns={c: f"home_{c}" for c in form_cols}).rename(columns={"team_key": "home_key"})

    away_form = panel_with_form[panel_with_form["is_home"] == 0][
        ["match_date", "team_key"] + form_cols
    ].rename(columns={c: f"away_{c}" for c in form_cols}).rename(columns={"team_key": "away_key"})

    df = home_rows.merge(home_form, on=["match_date", "home_key", "venue"], how="left")
    df = df.merge(away_form, on=["match_date", "away_key"], how="left")

    df = df.merge(ranking.rename(columns={"team_key": "home_key"}).add_prefix("home_rank_")
                  .rename(columns={"home_rank_home_key": "home_key"}), on="home_key", how="left")
    df = df.merge(ranking.rename(columns={"team_key": "away_key"}).add_prefix("away_rank_")
                  .rename(columns={"away_rank_away_key": "away_key"}), on="away_key", how="left")

    rank_cols = [c for c in df.columns if c.startswith("home_rank_") or c.startswith("away_rank_")]
    df[rank_cols] = df[rank_cols].fillna(df[rank_cols].mean(numeric_only=True))

    df["rank_perf_diff"] = df["home_rank_rank_avg_performance"] - df["away_rank_rank_avg_performance"]
    df["form_win_rate_diff"] = df["home_form_win_rate_5"] - df["away_form_win_rate_5"]
    df["form_margin_diff"] = df["home_form_avg_margin_5"] - df["away_form_avg_margin_5"]

    df["home_win"] = (df["home_result"] == "W").astype(int)
    df["is_draw"] = (df["home_result"] == "D").astype(int)

    df = df.rename(columns={"team_name": "home_team", "opponent": "away_team"})
    return df


MATCH_NUMERIC_FEATURES = [
    "home_form_win_rate_5", "home_form_avg_score_for_5", "home_form_avg_score_against_5",
    "home_form_avg_margin_5", "home_career_matches_played", "home_h2h_win_rate", "home_venue_win_rate",
    "away_form_win_rate_5", "away_form_avg_score_for_5", "away_form_avg_score_against_5",
    "away_form_avg_margin_5", "away_career_matches_played", "away_h2h_win_rate", "away_venue_win_rate",
    "home_rank_rank_avg_performance", "away_rank_rank_avg_performance",
    "rank_perf_diff", "form_win_rate_diff", "form_margin_diff",
]
MATCH_CATEGORICAL_FEATURES = ["venue"]


# --------------------------------------------------------------------------
# TOP PLAYER: rolling per-player form features
# --------------------------------------------------------------------------
def add_player_rolling_form(rb: pd.DataFrame, window: int = ROLLING_WINDOW) -> pd.DataFrame:
    rb = rb.sort_values(["player_id", "match_date"]).copy()
    g = rb.groupby("player_id", group_keys=False)
    rb["rolling_avg_fantasy_5"] = g["fantasy_points"].transform(
        lambda s: s.rolling(window, min_periods=1).mean().shift(1)
    )
    rb["career_avg_fantasy_to_date"] = g["fantasy_points"].transform(
        lambda s: s.expanding().mean().shift(1)
    )
    rb["rolling_avg_fantasy_5"] = rb["rolling_avg_fantasy_5"].fillna(LEAGUE_MEDIAN_FANTASY)
    rb["career_avg_fantasy_to_date"] = rb["career_avg_fantasy_to_date"].fillna(LEAGUE_MEDIAN_FANTASY)
    return rb


def attach_match_context(rb: pd.DataFrame, matches: pd.DataFrame) -> pd.DataFrame:
    """Bring in is_home / venue for each player-round row via the same
    normalised (team_key, opp_key, match_date) join key used everywhere."""
    ctx = matches[["team_key", "opp_key", "match_date", "home_away", "venue"]].copy()
    ctx["is_home"] = (ctx["home_away"] == "H").astype(int)
    ctx = ctx.drop(columns=["home_away"]).drop_duplicates(subset=["team_key", "opp_key", "match_date"])
    out = rb.merge(ctx, on=["team_key", "opp_key", "match_date"], how="left")
    out["is_home"] = out["is_home"].fillna(0).astype(int)
    out["venue"] = out["venue"].fillna("UNKNOWN_VENUE")
    return out


def attach_prior_season_form(rb: pd.DataFrame, seasonal: pd.DataFrame) -> pd.DataFrame:
    prior = seasonal.copy()
    prior["year"] = prior["year"] + 1  # this row's average becomes a feature for the *next* year
    prior = prior.rename(columns={"season_avg_fantasy": "prior_season_avg_fantasy"})
    out = rb.merge(prior, on=["player_id", "year"], how="left")
    out["has_prior_season_data"] = out["prior_season_avg_fantasy"].notna().astype(int)
    out["prior_season_avg_fantasy"] = out["prior_season_avg_fantasy"].fillna(LEAGUE_MEDIAN_FANTASY)
    return out


def attach_team_rank(rb: pd.DataFrame, ranking: pd.DataFrame) -> pd.DataFrame:
    r = ranking.rename(columns={"team_key": "team_key"})
    out = rb.merge(r.add_prefix("team_"), left_on="team_key", right_on="team_team_key", how="left")
    out = out.merge(r.add_prefix("opp_"), left_on="opp_key", right_on="opp_team_key", how="left")
    for c in ["team_rank_avg_performance", "opp_rank_avg_performance"]:
        out[c] = out[c].fillna(out[c].mean())
    return out


PLAYER_NUMERIC_FEATURES = [
    "rolling_avg_fantasy_5", "career_avg_fantasy_to_date", "career_game_count",
    "prior_season_avg_fantasy", "has_prior_season_data", "is_home",
    "team_rank_avg_performance", "opp_rank_avg_performance",
]
PLAYER_CATEGORICAL_FEATURES = ["team_key", "opp_key", "venue"]


@dataclass
class Split:
    train: pd.DataFrame
    test: pd.DataFrame
    cutoff_date: pd.Timestamp
