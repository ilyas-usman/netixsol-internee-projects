"""
resolvers.py — Week 6 / Day 4 — Task 3 (input resolution)
============================================================
Single shared place for "what did the user actually mean by that team
name" so retrieval_node and prediction_node can't drift into resolving
aliases two different ways.

Two-stage resolution, chained on purpose:
  1. tools.py._normalize_team()  — nickname/alias -> canonical name as it
     appears in team_matches_home_away_raw.csv (e.g. "pies" -> "collingwood
     magpies"). This is the layer that knows "Pies", "Cats", "GWS", etc.
  2. common.py.normalize_team()  — casing/whitespace normalisation into the
     UPPERCASE key predict.py's models were actually trained on (e.g.
     "collingwood magpies" -> "COLLINGWOOD MAGPIES"). predict.py's
     _validate_team() already calls this internally, so stage 2 doesn't
     strictly need to be called again before handing off to predict.py —
     it's exposed here mainly so prediction_node can pre-check membership
     and produce a clarification question BEFORE calling predict.py,
     rather than catching predict.py's ValueError after the fact.

Both stages return "unchanged input, lowercased" on no match rather than
raising, so the caller can decide what "not found" means for its context
(NOT_FOUND string for a retrieval tool vs. a clarification question for a
prediction).
"""
from __future__ import annotations

import common as C
import tools as T


def resolve_team_alias(raw_name: str) -> str:
    """Nickname/short-name -> canonical dataset display name, e.g.
    'Pies' -> 'collingwood magpies', 'Dogs' -> 'w. bulldogs'.
    Falls back to the lowercased input unchanged if nothing matches."""
    return T._normalize_team(raw_name)


def is_known_team(raw_name: str, known_teams_upper: list[str]) -> bool:
    """Check a raw user-typed team name against predict.py's meta['known_teams']
    (an UPPERCASE list) by running it through the full two-stage resolution."""
    alias_resolved = resolve_team_alias(raw_name)
    canonical_key = C.normalize_team(alias_resolved)
    return canonical_key in known_teams_upper


def resolve_team_for_prediction(raw_name: str) -> str:
    """Resolve a raw user-typed team name into a string safe to pass
    straight into predict_match_winner / predict_top_player (which call
    C.normalize_team internally). We only need stage 1 (alias expansion)
    here — predict.py handles stage 2 itself and will raise a clean
    ValueError if the result still isn't a known team."""
    return resolve_team_alias(raw_name)
