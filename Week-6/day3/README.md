# AFL Domain-Scoped Chat Agent — Week 6, Day 3 Submission

Retrieval, guardrails, and grounding for a LangChain-based AFL chat assistant.
This README maps each task in the brief to the file(s) that satisfy it, and
lists what's still outstanding before final submission.

## File → Task map

| File | Tasks covered | What it contains |
|---|---|---|
| `guardrail-Report.md` | **Tasks 1, 3, 4, 5** | Consolidated, fact-checked report covering all four tasks in one document — scope/refusal design with verbatim quotes, the grounding-check mechanism and its one real flag, the Task 4 memory transcript summary, and the Task 5 24-prompt score table with failure patterns and fixes. All numbers and quotes are checked against the actual `guadrails.py` and `agent.py` transcripts. |
| `task1-concept.md` | **Task 1** | Fuller version of the Task 1 section — same content as in `guardrail-Report.md`, standalone. |
| `tools.py` | **Task 2** | Structured pandas retrieval tools over the real AFL dataset: `get_player_round_stats`, `get_player_season_average`, `get_player_season_total`, `get_team_head_to_head`, `get_match_result` — 5 tools total. Plus team-name alias normalization (`_normalize_team`/`TEAM_ALIASES`) and error-safe lookups (every tool wraps its body in try/except so a bad input returns an `ERROR:`/`NOT_FOUND:` string instead of crashing the agent turn). Includes an optional, currently-inactive semantic/vector tool template (`build_semantic_tool`) with the justification for why it's not wired in — the provided dataset is fully structured CSVs, no free-text articles/match reports to index. |
| `agent.py` | **Tasks 1, 3, 4** | `SYSTEM_PROMPT` (the operative scope definition, 7 rules), `create_agent` wiring with all 5 Task 2 tools, `InMemorySaver`-backed conversation memory, and `verify_grounding()` — the number-level grounding check described in Task 3 (float-normalized comparison, user-input exclusion, and a skip for clarifying questions ending in "?"). `__main__` defines the required 4–5 turn memory conversation (`core_turns`) plus an extended `guardrail_turns` set. |
| `chat_interactive.py` | Manual testing | REPL that imports `build_agent`, `ask`, and `ToolCallLogger` straight from `agent.py` (no duplicated logic) so you can type your own questions live instead of only running the scripted turns. Supports `/new` (fresh thread), `/thread`, `/log` (see grounded tool outputs), `/quit`. |
| `task4-memeory-transcript.md` | **Task 4** | Fuller version of the Task 4 section — same content as in `guardrail-Report.md`, standalone, with the extended `guardrail_turns` scoring included. |
| `guadrails.py` | **Task 5** | Consolidated, fact-checked report covering all four tasks in one document —
scope/refusal design with verbatim quotes, the grounding-check mechanism
and its reproduced/fixed false-positive, the Task 4 memory transcript
summary, and the Task 5 24-prompt score table with failure patterns and
fixes. |
| `README.md` | — | This file. |

**Note:** an earlier draft file, `task5_eval_report.md`, used fictional
sample data (a 2026 season, different players) predating the real dataset
integration and is superseded by `guardrail-Report.md`'s Task 5 section,
which reports the actual `guadrails.py` run against the real dataset and
model. `task5_eval_report.md` should not be included in the final
submission — its numbers and failure-pattern list describe a different,
earlier version of the agent and will conflict with the real report if
both are read side by side.

## How to run it

```bash
pip install --upgrade langchain langchain-groq langgraph python-dotenv pandas
```

Create a `.env` file next to `agent.py`:

```
GROQ_API_KEY=gsk_your-actual-key-here
```

Point at your dataset (defaults to a `dataset/` folder next to `agent.py`
containing `final_enriched_dataset.csv`, `afl_players_info_raw.csv`, and
`team_matches_home_away_raw (1).csv`), or override with:

```
AFL_DATA_DIR=/path/to/your/dataset
```

Then run:

```bash
python agent.py
```

This executes both `core_turns` (the Task 4 memory demo: team →
head-to-head, player → round stats, follow-up round, season-average
comparison, mid-thread off-topic guardrail check) and `guardrail_turns`
(alias robustness, finals-round codes, NOT_FOUND path, ambiguous
clarification, prompt injection, off-topic redirect, memory recovery after
a decline).

To run the full Task 5 guardrail evaluation (24 prompts across 6
categories, with an auto-generated pass/fail-style summary table):

```bash
python guadrails.py
```

To ask your own questions live instead of running the scripted turns:

```bash
python chat_interactive.py
```

This opens a REPL against the same agent, tools, memory, and grounding
check as `agent.py` — it just lets you drive the conversation by hand.
Type `/new` for a fresh thread, `/log` to see every grounded tool output
from the session, `/quit` to exit.

## Outstanding before final submission

- [x] Run `agent.py` and capture its console output as the Task 4
      transcript. Done — see `task4-memeory-transcript.md`. 12/13 turns
      passed cleanly, zero grounding warnings; one design observation
      logged on rule 3 (ambiguity handling gets overridden when the thread
      already has resolvable context).
- [x] Run the full 24-prompt Task 5 suite via `guadrails.py` and record
      real results in `guardrail-Report.md` — done; 24/24 correctly scoped,
      0 grounding flags, 0 crashes.
- [x] Add `get_player_season_total` to `tools.py` to cover "total X this
      season" / "how many X did he get in <year>" phrasing that the
      average-only tool couldn't answer — done, registered in
      `STRUCTURED_TOOLS`.
- [x] Run adversarial prompts #8 and #9 from `task1-concept.md`
      (the "developer mode" override and the multi-turn compliance-priming
      attempt) — done; both passed and are documented in `guardrail-Report.md`.
- [x] Apply the Pattern 8 grounding fix — done. The
      "Explain what a 'behind' is in AFL" test was re-run with no
      `[GROUNDING WARNING]`; the final behavior is documented in
      `guardrail-Report.md`.
