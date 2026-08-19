"""
Task 2 — Retrieval layer over AFL data.

Design decision (structured vs. semantic):
- All numeric stats and results (disposals, scores, head-to-head records,
  season averages/totals) go through STRUCTURED lookups directly against
  the pandas dataframes loaded from the real dataset CSVs. Sports stats
  are discrete, exact values sitting in known columns — running them
  through a vector store would mean re-deriving a number from an
  embedding's nearest-neighbor text chunk, which is exactly how you get a
  hallucinated or slightly-wrong figure. A pandas/SQL query returns the
  *actual* cell.
- Semantic (vector) retrieval is reserved for free-text content only —
  match reports, commentary, injury news, historical write-ups — where
  there's no fixed schema and the useful unit is a paragraph of meaning,
  not a value. The provided dataset here is all structured CSVs
  (players_info, round-by-round stats, seasonal stats, team matches), so
  the semantic tool below is included as an optional/example tool that
  activates only if unstructured text files are present.

Dataset coverage (Task 1 scope check): this module wires in 3 of the
dataset's 17 CSVs — final_enriched_dataset.csv (player round-by-round
stats), afl_players_info_raw.csv (player_id -> name join), and
team_matches_home_away_raw (1).csv (team results / head-to-head). That
covers every numeric part of Task 1's stated scope (players, stats,
teams, matches). AFL rules/terminology/history questions are answered
directly by the model with no tool call, since they involve no dataset
numbers to ground. The other 14 dataset files (afl_players_seasonal_
stats_raw.csv, team_ranking.csv, venue_performance.csv, etc.) are not
currently wired in — nothing in Task 1's scope strictly requires them,
but they're candidates if you want richer coverage later (e.g. official
pre-aggregated season totals instead of summing round-by-round rows).

Paths are resolved relative to this file's own location, never hardcoded
absolute paths — so the project still works if it's cloned to a different
machine or moved to a different folder. By default this looks for a
`dataset/` folder sitting next to this script (i.e. Week-6/day3/dataset,
alongside agent.py and tools.py) and expects your real filenames:
final_enriched_dataset.csv and 'team_matches_home_away_raw (1).csv'.

You can override the dataset location without touching this file at all
by setting an AFL_DATA_DIR environment variable (e.g. in your .env file):
  AFL_DATA_DIR=D:/Netixsol_Intern_Projects/Week-6/day3/dataset
  (forward slashes work fine on Windows and avoid escape-sequence issues)
"""

import os
import pandas as pd
from langchain.tools import tool

# Base directory: this file's own folder, so it never depends on where the
# script is launched from or which machine it runs on.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))

# Resolution order: AFL_DATA_DIR env var (if set) -> ./dataset next to this
# file -> ./data next to this file (fallback, matches the sample data).
DATA_DIR = os.environ.get("AFL_DATA_DIR")
if not DATA_DIR:
    _dataset_candidate = os.path.join(_THIS_DIR, "dataset")
    _data_candidate = os.path.join(_THIS_DIR, "data")
    DATA_DIR = _dataset_candidate if os.path.isdir(_dataset_candidate) else _data_candidate

PLAYER_STATS_FILE = os.path.join(DATA_DIR, "final_enriched_dataset.csv")
PLAYER_INFO_FILE = os.path.join(DATA_DIR, "afl_players_info_raw.csv")
TEAM_MATCHES_FILE = os.path.join(DATA_DIR, "team_matches_home_away_raw (1).csv")

# Fallback to the small sample files (used for local testing / demos) if
# the real dataset files aren't present under DATA_DIR.
if not os.path.isfile(PLAYER_STATS_FILE):
    PLAYER_STATS_FILE = os.path.join(DATA_DIR, "player_round_stats.csv")
if not os.path.isfile(TEAM_MATCHES_FILE):
    TEAM_MATCHES_FILE = os.path.join(DATA_DIR, "team_matches.csv")

_player_df = pd.read_csv(PLAYER_STATS_FILE)
_matches_df = pd.read_csv(TEAM_MATCHES_FILE)

# --- Real-dataset column alignment -----------------------------------------
# final_enriched_dataset.csv uses 'year' where the rest of this module says
# 'season' — normalise that here so every tool function below can just use
# 'season' consistently, regardless of which dataset (real or sample) loaded.
if "year" in _player_df.columns and "season" not in _player_df.columns:
    _player_df = _player_df.rename(columns={"year": "season"})

# team_matches_home_away_raw (1).csv is ONE ROW PER TEAM, PER MATCH — every
# match appears twice (once from each team's perspective) — with columns:
# ['id','team_name','round','match_date','year','home_away','opponent',
#  'team_quarter_scores','team_score','opponent_quarter_scores',
#  'opponent_score','result','margin','venue','crowd','team_goals_kicked',
#  'team_behinds','opponent_goals_kicked','opponent_behinds']
# There is no home_team/away_team/home_score/away_score split — apply the
# same 'year' -> 'season' rename here so the tool functions below can use
# 'season' consistently, same as the player dataframe.
if "year" in _matches_df.columns and "season" not in _matches_df.columns:
    _matches_df = _matches_df.rename(columns={"year": "season"})

# The real CSV has inconsistent leading/trailing whitespace and stray tabs
# in team_name/opponent (e.g. '\tCarlton Blues', ' Adelaide Crows ') — strip
# both so equality checks aren't silently broken by whitespace.
for _col in ("team_name", "opponent"):
    if _col in _matches_df.columns:
        _matches_df[_col] = _matches_df[_col].astype(str).str.strip()

# The dataset stores full/official club names ('Carlton Blues',
# 'W. Bulldogs', 'Greater Western Sydney Giants'), not the shorter names
# people actually type ('Carlton', 'Western Bulldogs', 'GWS'). Map common
# short names/nicknames to the exact strings that appear in the data.
TEAM_ALIASES = {
    "adelaide": "adelaide crows", "crows": "adelaide crows",
    "brisbane lions": "brisbane lions", "lions": "brisbane lions",
    "brisbane bears": "brisbane bears",
    "carlton": "carlton blues", "blues": "carlton blues",
    "collingwood": "collingwood magpies", "magpies": "collingwood magpies",
    "essendon": "essendon bombers", "bombers": "essendon bombers",
    "fitzroy": "fitzroy lions",
    "fremantle": "fremantle dockers", "dockers": "fremantle dockers",
    "geelong": "geelong cats", "cats": "geelong cats",
    "gold coast": "gold coast suns", "suns": "gold coast suns",
    "gws": "greater western sydney giants", "gws giants": "greater western sydney giants",
    "giants": "greater western sydney giants",
    "hawthorn": "hawthorn hawks", "hawks": "hawthorn hawks",
    "melbourne": "melbourne demons", "demons": "melbourne demons",
    "north melbourne": "north melbourne kangaroos", "kangaroos": "north melbourne kangaroos",
    "port adelaide": "port adelaide power", "power": "port adelaide power",
    "richmond": "richmond tigers", "tigers": "richmond tigers",
    "st kilda": "st kilda saints", "saints": "st kilda saints",
    "sydney": "sydney swans", "swans": "sydney swans",
    "western bulldogs": "w. bulldogs", "footscray": "w. bulldogs", "bulldogs": "w. bulldogs",
    "west coast": "west coast eagles", "eagles": "west coast eagles",
}

_CANONICAL_TEAMS = set(_matches_df["team_name"].str.lower()) if "team_name" in _matches_df.columns else set()


def _normalize_team(name: str) -> str:
    """Resolve a user-typed team name to whatever exact string is used in
    the dataset. Tries: exact match -> alias map -> substring fallback.
    Returns the lowercased canonical name, or the normalized input
    unchanged if nothing matches (so the caller still gets a clean
    NOT_FOUND instead of a crash)."""
    n = _norm(name)
    if n in _CANONICAL_TEAMS:
        return n
    if n in TEAM_ALIASES:
        return TEAM_ALIASES[n]
    # substring fallback, e.g. "carlton" -> "carlton blues" for any alias
    # not explicitly listed above
    for canonical in _CANONICAL_TEAMS:
        if n in canonical or canonical in n:
            return canonical
    return n

# final_enriched_dataset.csv has no player name column, only a numeric
# 'player_id' — join against afl_players_info_raw.csv (id -> player_name)
# to make player-name lookups possible. Only attempted against the real
# dataset; the small sample CSV already has a 'player' name column and
# doesn't need this join.
if "player_id" in _player_df.columns and os.path.isfile(PLAYER_INFO_FILE):
    _players_info_df = pd.read_csv(PLAYER_INFO_FILE)
    _players_info_df = _players_info_df.rename(columns={"id": "_info_id"})
    _player_df = _player_df.merge(
        _players_info_df[["_info_id", "player_name", "player_full_name"]],
        left_on="player_id",
        right_on="_info_id",
        how="left",
    )


def _match_player(df: pd.DataFrame, player_name: str) -> pd.Series:
    """Return a boolean mask matching a player by whichever name column is
    available in the loaded dataframe (sample data uses 'player'; the real
    dataset uses 'player_name' / 'player_full_name' from the join above)."""
    norm = _norm(player_name)
    mask = pd.Series(False, index=df.index)
    for col in ("player", "player_name", "player_full_name"):
        if col in df.columns:
            mask = mask | (df[col].astype(str).str.lower() == norm)
    return mask


def _player_display_name(row) -> str:
    for col in ("player", "player_full_name", "player_name"):
        if col in row.index and pd.notna(row[col]):
            return row[col]
    return "Unknown player"


def _norm(s: str) -> str:
    return str(s).strip().lower()


_TRACKED_STATS = {"disposals", "kicks", "handballs", "marks", "tackles", "goals", "behinds"}


@tool
def get_player_round_stats(player_name: str, season: int, round_number: str) -> str:
    """Look up a single AFL player's exact stat line for one specific round
    of one specific season (disposals, kicks, handballs, marks, tackles,
    goals, behinds). round_number is a string: regular rounds are plain
    numbers as text ('1', '2', '21'), finals use codes ('EF', 'QF', 'SF',
    'PF', 'GF'). Use this whenever the user asks about a player's
    performance in a named/implied round. Returns 'NOT_FOUND' with no
    invented numbers if no matching row exists in the dataset."""
    try:
        df = _player_df
        # 'round' is stored as a string in the real dataset ('1'..'24' plus
        # finals codes 'EF'/'QF'/'SF'/'PF'/'GF'), not an int — comparing
        # against a bare int always silently misses every row. Normalize
        # both sides to a stripped string for the comparison.
        round_str = str(round_number).strip()
        match = df[
            _match_player(df, player_name)
            & (df["season"] == season)
            & (df["round"].astype(str).str.strip() == round_str)
        ]
        if match.empty:
            return (
                f"NOT_FOUND: no row in the dataset for {player_name}, "
                f"season {season}, round {round_number}."
            )
        row = match.iloc[0]
        return (
            f"{_player_display_name(row)} ({row['team']}) — {row['season']} Round {row['round']} "
            f"vs {row['opponent']}: {row['disposals']} disposals "
            f"({row['kicks']} kicks, {row['handballs']} handballs), "
            f"{row['marks']} marks, {row['tackles']} tackles, "
            f"{row['goals']} goals {row['behinds']} behinds."
        )
    except Exception as e:
        # A tool that raises kills the whole agent turn (and the whole
        # script, since LangGraph propagates it). Never let a malformed or
        # unexpected input crash the run — surface it as data the model can
        # relay honestly instead.
        return f"ERROR: could not look up {player_name}'s round stats ({type(e).__name__}: {e})."


@tool
def get_player_season_average(player_name: str, season: int, stat: str = "disposals") -> str:
    """Compute an AFL player's AVERAGE (mean per round) for a given stat
    (default: 'disposals'; also supports kicks, handballs, marks, tackles,
    goals, behinds) across every round on record for that season. Use
    this for 'career average', 'season average', 'per game', or 'compare
    to his average' follow-up questions. For a SEASON TOTAL instead (e.g.
    'how many total disposals', 'total behinds this season'), use
    get_player_season_total instead — do not compute a total by
    multiplying this average by a round count, always call the total tool
    directly. Averages are computed live from the dataset, never recalled
    from memory."""
    try:
        df = _player_df
        stat = stat.lower().strip()
        if stat not in _TRACKED_STATS:
            return f"NOT_FOUND: '{stat}' is not a tracked stat column."
        subset = df[_match_player(df, player_name) & (df["season"] == season)]
        if subset.empty:
            return f"NOT_FOUND: no rows for {player_name} in season {season}."
        avg = subset[stat].mean()
        n = len(subset)
        return f"{player_name} averaged {avg:.1f} {stat} across {n} rounds in {season}."
    except Exception as e:
        return f"ERROR: could not compute {player_name}'s season average ({type(e).__name__}: {e})."


@tool
def get_player_season_total(player_name: str, season: int, stat: str = "disposals") -> str:
    """Compute an AFL player's SEASON TOTAL (summed across every round on
    record) for a given stat (default: 'disposals'; also supports kicks,
    handballs, marks, tackles, goals, behinds). Use this whenever the user
    asks for a 'total', 'how many X in total this season', or a plain
    'how many X did he get in <year>' without specifying a single round —
    that phrasing means a season total, NOT an average. Never estimate a
    total by multiplying an average by a guessed number of games; this
    tool sums the actual rows on record and also reports how many rounds
    that total covers, so an incomplete season is visible in the answer
    rather than presented as a full-season figure."""
    try:
        df = _player_df
        stat = stat.lower().strip()
        if stat not in _TRACKED_STATS:
            return f"NOT_FOUND: '{stat}' is not a tracked stat column."
        subset = df[_match_player(df, player_name) & (df["season"] == season)]
        if subset.empty:
            return f"NOT_FOUND: no rows for {player_name} in season {season}."
        total = subset[stat].sum()
        n = len(subset)
        return (
            f"{player_name} recorded a total of {int(total)} {stat} across "
            f"{n} rounds on record in {season}. (This reflects only the "
            f"{n} rounds present in the dataset for that season — if the "
            f"real season had more rounds than that, this total may be "
            f"partial rather than the full-season figure.)"
        )
    except Exception as e:
        return f"ERROR: could not compute {player_name}'s season total ({type(e).__name__}: {e})."


@tool
def get_team_head_to_head(team_a: str, team_b: str) -> str:
    """Get the exact head-to-head win/loss record between two AFL teams,
    computed from every match row on record where these two teams played
    each other. Use this for 'record vs' or 'who usually wins' style
    questions. Never estimate this from memory."""
    try:
        df = _matches_df
        a, b = _normalize_team(team_a), _normalize_team(team_b)

        if a == b:
            return f"NOT_FOUND: '{team_a}' and '{team_b}' resolve to the same team — no head-to-head against itself."

        # One row per team per match: team_a's perspective rows (team_name=a,
        # opponent=b) already cover every meeting exactly once — no need to
        # also scan team_b's mirrored rows, and no home_team/away_team split
        # exists in this dataset.
        games = df[
            (df["team_name"].str.lower() == a) & (df["opponent"].str.lower() == b)
        ]
        if games.empty:
            return f"NOT_FOUND: no recorded matches between {team_a} and {team_b}."

        a_wins = int((games["team_score"] > games["opponent_score"]).sum())
        b_wins = int((games["team_score"] < games["opponent_score"]).sum())
        draws = int((games["team_score"] == games["opponent_score"]).sum())
        first_season = int(games["season"].min())
        last_season = int(games["season"].max())

        games_sorted = games.sort_values(["season", "round"])
        lines = []
        for _, g in games_sorted.iterrows():
            lines.append(
                f"{g['season']} R{g['round']}: {g['team_name']} {g['team_score']} - "
                f"{g['opponent_score']} {g['opponent']}"
            )

        # Cap the listed matches — a long-running rivalry (80+ games) dumping
        # every line ballooned tool-output size, which was eating enough
        # tokens per turn to trip the Groq free-tier rate limit once
        # conversation history started accumulating across turns. Give the
        # model an explicit, grounded season range instead of the full list,
        # so it has a real number to cite rather than inventing a start date
        # like "the early 1900s".
        MAX_LISTED = 15
        note = ""
        if len(lines) > MAX_LISTED:
            note = f" (showing the most recent {MAX_LISTED} of {len(games)} games)"
            lines = lines[-MAX_LISTED:]

        summary = (
            f"Head-to-head, {len(games)} recorded games spanning {first_season}-{last_season} — "
            f"{team_a} {a_wins} wins, {team_b} {b_wins} wins"
            + (f", {draws} draws" if draws else "") + f".{note}\n"
        )
        return summary + "\n".join(lines)
    except Exception as e:
        return f"ERROR: could not compute head-to-head for {team_a} vs {team_b} ({type(e).__name__}: {e})."


@tool
def get_match_result(season: int, round_number: int, team: str) -> str:
    """Look up the exact final score of a specific AFL team's match in a
    given season and round. Use this for 'what happened in round X' type
    questions."""
    try:
        df = _matches_df
        t = _normalize_team(team)
        match = df[
            (df["season"] == season)
            & (df["round"].astype(str).str.lower() == str(round_number).lower())
            & (df["team_name"].str.lower() == t)
        ]
        if match.empty:
            return f"NOT_FOUND: no match row for {team}, season {season}, round {round_number}."
        row = match.iloc[0]
        return (
            f"{row['season']} Round {row['round']} at {row['venue']}: "
            f"{row['team_name']} {row['team_score']} - {row['opponent_score']} {row['opponent']}. "
            f"Result: {row['result']} (margin {row['margin']})."
        )
    except Exception as e:
        return f"ERROR: could not look up match result for {team}, season {season}, round {round_number} ({type(e).__name__}: {e})."


STRUCTURED_TOOLS = [
    get_player_round_stats,
    get_player_season_average,
    get_player_season_total,
    get_team_head_to_head,
    get_match_result,
]


# ---------------------------------------------------------------------------
# Optional semantic tool — only wire this in if you actually have unstructured
# text (match reports, articles). Left here as a ready-to-use template.
# ---------------------------------------------------------------------------
def build_semantic_tool(text_docs_dir: str):
    """Build a Chroma-backed semantic retrieval tool over a directory of
    plain-text match reports / articles. Returns a LangChain tool, or None
    if the directory doesn't exist or has no files (nothing to index)."""
    if not os.path.isdir(text_docs_dir) or not os.listdir(text_docs_dir):
        return None

    from langchain_community.document_loaders import DirectoryLoader
    from langchain_community.vectorstores import Chroma
    from langchain_openai import OpenAIEmbeddings  # swap for your embedding provider
    from langchain.text_splitter import RecursiveCharacterTextSplitter

    loader = DirectoryLoader(text_docs_dir, glob="**/*.txt")
    docs = loader.load()
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    chunks = splitter.split_documents(docs)
    vectordb = Chroma.from_documents(chunks, OpenAIEmbeddings())
    retriever = vectordb.as_retriever(search_kwargs={"k": 4})

    @tool
    def search_afl_articles(query: str) -> str:
        """Semantic search over unstructured AFL match reports / articles /
        commentary. Use ONLY for qualitative context (narrative, injury
        news, analysis) — never for exact stats or scores, which must come
        from the structured tools instead."""
        results = retriever.invoke(query)
        if not results:
            return "NOT_FOUND: no relevant articles indexed."
        return "\n---\n".join(d.page_content[:500] for d in results)

    return search_afl_articles