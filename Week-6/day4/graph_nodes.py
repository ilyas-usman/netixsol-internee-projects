"""
graph_nodes.py — Week 6 / Day 4 — Tasks 3 & 4
================================================
Every node except the router (router.py) and the graph wiring (graph.py).

    retrieval_node    -- dispatches to one of the 7 Day-3 structured tools
    prediction_node   -- calls the Task-3 prediction wrappers
    factual_node      -- direct LLM answer, no tool (rules/trivia, no numbers)
    off_topic_node    -- fixed refusal + redirect, no LLM call needed
    validation_node   -- Task 4: checks tool/model output, routes to
                          clarification or fallback instead of guessing
    clarification_node-- Task 4: ends the turn with a clarifying question
    response_formatting_node -- Task 1: single convergence point; this is
                          the ONLY place that turns tool_results into the
                          text the user sees, so the probabilistic-framing
                          requirement on predictions lives here, once,
                          unconditionally.
"""
from __future__ import annotations

from typing import Optional

from langchain_groq import ChatGroq

import tools as T
import team_stats_tools as TS
from prediction_tools import predict_match_winner_tool, predict_top_player_tool
from state import AgentState

RETRIEVAL_TOOL_MAP = {
    "get_player_round_stats": T.get_player_round_stats,
    "get_player_season_average": T.get_player_season_average,
    "get_player_season_total": T.get_player_season_total,
    "get_round_leader": T.get_round_leader,
    "get_season_leader": T.get_season_leader,
    "get_team_head_to_head": T.get_team_head_to_head,
    "get_match_result": T.get_match_result,
    "get_team_win_rate_leader": TS.get_team_win_rate_leader,
}


# --------------------------------------------------------------------------
# retrieval_node
# --------------------------------------------------------------------------
def retrieval_node(state: AgentState) -> dict:
    entities = state.get("entities", {})
    tool_name = entities.get("retrieval_tool")

    if tool_name not in RETRIEVAL_TOOL_MAP:
        return {
        "tool_results": [f"ERROR: router did not select a valid retrieval tool ('{tool_name}')."],
        "validation_status": "needs_clarification",
        "clarification_question": (
            "I'm not sure exactly what you're asking for -- could you be more "
            "specific? For example: a player's stats for a game or season, a "
            "comparison between two players, a season/round leader in a stat, "
            "or a team's win rate or head-to-head record."
            ),
        }

    tool = RETRIEVAL_TOOL_MAP[tool_name]
    args = {}
    if tool_name == "get_player_round_stats":
        args = {"player_name": entities.get("player_name"), "season": entities.get("season"),
                 "round_number": entities.get("round_number")}
    elif tool_name in ("get_player_season_average", "get_player_season_total"):
        args = {"player_name": entities.get("player_name"), "season": entities.get("season"),
                 "stat": entities.get("stat") or "disposals"}
    elif tool_name == "get_round_leader":
        args = {"season": entities.get("season"), "round_number": entities.get("round_number"),
                 "stat": entities.get("stat") or "disposals"}
    elif tool_name == "get_season_leader":
        args = {"season": entities.get("season"), "stat": entities.get("stat") or "goals"}
    elif tool_name == "get_team_head_to_head":
        args = {"team_a": entities.get("team_a"), "team_b": entities.get("team_b")}
    elif tool_name == "get_match_result":
        args = {"season": entities.get("season"), "round_number": entities.get("round_number"),
                 "team": entities.get("team_a")}
    elif tool_name == "get_team_win_rate_leader":
        args = {"season_start": entities.get("season"), "top_n": 5}
        if entities.get("season_end") is not None:
            args["season_end"] = entities.get("season_end")

    missing = [k for k, v in args.items() if v is None]
    if missing:
        friendly_prompts = {
            "season": "Which season/year are you asking about?",
            "round_number": "Which round?",
            "player_name": "Which player did you mean?",
            "team_a": "Which team did you mean?",
            "stat": "Which stat are you interested in (disposals, goals, tackles, etc.)?",
        }
        question = " ".join(friendly_prompts.get(m, f"Could you specify {m}?") for m in missing)
        return {
            "tool_results": [f"ERROR: missing required info for {tool_name}: {', '.join(missing)}."],
            "validation_status": "needs_clarification",
            "clarification_question": question,
        }

    result = tool.invoke(args)
    return {"tool_results": [result]}


# --------------------------------------------------------------------------
# prediction_node
# --------------------------------------------------------------------------
def prediction_node(state: AgentState) -> dict:
    entities = state.get("entities", {})
    ptype = entities.get("prediction_type")

    if ptype == "other_unsupported":
        return {
            "validation_status": "out_of_scope",
            "validation_message": (
                "This asks for a prediction type we don't have a model for. We only "
                "predict: (1) match winner, and (2) top fantasy-point scorer. We don't "
                "model specific stats like 'most goals' or 'final margin'."
            ),
        }

    if ptype == "match_winner":
        team_a, team_b = entities.get("team_a"), entities.get("team_b")
        if not team_a or not team_b:
            return {
                "validation_status": "needs_clarification",
                "clarification_question": "Which two teams do you want a match-winner prediction for?",
            }
        outcome = predict_match_winner_tool(
            team_a, team_b, date_hint=entities.get("date_hint"), venue=entities.get("venue"),
        )
        if not outcome["ok"]:
            return {"tool_results": [f"ERROR: {outcome['error']}"], "validation_status": "error"}
        return {"tool_results": [outcome["result"]], "prediction_payload": outcome["result"]}

    if ptype == "top_player":
        outcome = predict_top_player_tool(
            team_raw=entities.get("team_a"), opponent_raw=entities.get("team_b"),
            venue=entities.get("venue"), date_hint=entities.get("date_hint"), top_n=5,
        )
        if not outcome["ok"]:
            return {"tool_results": [f"ERROR: {outcome['error']}"], "validation_status": "error"}
        return {"tool_results": [outcome["result"]], "prediction_payload": outcome["result"]}

    return {
        "validation_status": "needs_clarification",
        "clarification_question": "Are you asking who will win a match, or who will top-score?",
    }


# --------------------------------------------------------------------------
# factual_node -- no tool call, no numbers, so no grounding/validation needed
# --------------------------------------------------------------------------
FACTUAL_SYSTEM_PROMPT = """You are an AFL rules/history/terminology assistant. Answer
briefly and accurately, ONLY about fixed rules, terminology, or long-settled history
(e.g. "what is a behind worth", "why is the MCG called that", "when did the AFL start").

Never state or imply anything about a team's current form, this season's results,
standings, injuries, coaching tactics, or personnel -- even in vague/qualitative terms
("solid contender", "strong midfield", "resilient this season"). You have no live data
source and no access to the current season at all, so any such claim is a guess dressed
up as fact.

If the question is actually asking about a specific team, player, season, or "how are
they doing" in any form, do NOT answer it. Instead respond with exactly: "That's a
retrieval question, not a rules question -- I don't have a live sense of current form,
but I can look up actual recorded stats or results if you tell me the player/team and
season." Stay strictly on AFL topics."""


def factual_node(state: AgentState) -> dict:
    llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0)
    resp = llm.invoke([
        {"role": "system", "content": FACTUAL_SYSTEM_PROMPT},
        {"role": "user", "content": state["user_query"]},
    ])
    return {"tool_results": [resp.content], "validation_status": "ok"}


# --------------------------------------------------------------------------
# off_topic_node -- fixed copy, no LLM call needed (cheaper + unconditional)
# --------------------------------------------------------------------------
def off_topic_node(state: AgentState) -> dict:
    return {
        "tool_results": [
            "That's outside what I can help with -- I'm scoped to AFL stats, results, "
            "and predictions. Happy to help with an AFL question instead."
        ],
        "validation_status": "ok",
    }


# --------------------------------------------------------------------------
# validation_node (Task 4)
# --------------------------------------------------------------------------
def validation_node(state: AgentState) -> dict:
    """Runs after retrieval_node or prediction_node. Decides: format
    normally, ask for clarification, or hand back the out-of-scope
    message -- never lets a NOT_FOUND/ERROR string flow straight into a
    'confident-sounding' final answer."""
    status = state.get("validation_status")
    if status in ("needs_clarification", "out_of_scope", "error"):
        if state.get("clarification_question"):
            return {}  # already set upstream (e.g. prediction_node's "which two teams?")

        msg = state.get("validation_message")
        if not msg:
            # error status with no explicit message -- pull the reason
            # straight out of the ERROR: string a tool/prediction wrapper
            # produced, so the user sees the real cause, not a generic line.
            results = state.get("tool_results", [])
            if results and isinstance(results[0], str) and results[0].startswith("ERROR"):
                msg = results[0].split(":", 1)[-1].strip()
        if not msg:
            msg = ("I couldn't resolve one of the names in your question -- could you "
                   "confirm the exact team or player name?")
        return {"clarification_question": msg}

    results = state.get("tool_results", [])
    if not results:
        return {"validation_status": "error", "validation_message": "No tool result was produced."}

    first = results[0]
    text = first if isinstance(first, str) else str(first)
    if text.startswith("NOT_FOUND"):
        return {
            "validation_status": "needs_clarification",
            "clarification_question": (
                f"I couldn't find that in the dataset ({text.split(':', 1)[-1].strip()}). "
                "Could you double-check the name, season, or round?"
            ),
        }
    if text.startswith("ERROR"):
        return {
            "validation_status": "needs_clarification",
            "clarification_question": (
                f"I hit a snag resolving that ({text.split(':', 1)[-1].strip()}). "
                "Could you rephrase or confirm the exact name?"
            ),
        }

    return {"validation_status": "ok"}


# --------------------------------------------------------------------------
# clarification_node (Task 4)
# --------------------------------------------------------------------------
def clarification_node(state: AgentState) -> dict:
    """Ends the turn with a clarifying question instead of guessing. In a
    chat UI this is the correct place to stop (not an in-turn graph
    cycle back to the router) -- we need the user's actual next message,
    which arrives as a new graph invocation against the same checkpointed
    thread, not as synthetic state we could fabricate ourselves."""
    question = state.get("clarification_question") or "Could you clarify that?"
    return {"final_response": question}


# --------------------------------------------------------------------------
# response_formatting_node (Task 1 convergence point)
# --------------------------------------------------------------------------
def _format_prediction(payload: dict) -> str:
    if "predicted_winner" in payload:  # match winner
        lines = [
            f"**Prediction: {payload['predicted_winner']}** "
            f"({payload['home_team']} {payload['home_win_probability']:.0%} vs "
            f"{payload['away_team']} {payload['away_win_probability']:.0%})",
            f"Venue: {payload['venue']} | Model: {payload['model']}",
        ]
        if payload.get("top_features"):
            lines.append("Most influential inputs: " + "; ".join(payload["top_features"]))
        if not payload.get("used_live_fixture_date"):
            lines.append(
                f"_Note: based on data through {payload['as_of_date']} — there's no live "
                "fixture calendar in this dataset, so this reflects current form rather "
                "than a specific scheduled match date._"
            )
        lines.append(
            "_This is a probabilistic model estimate, not a guaranteed outcome — treat it "
            "as one input among many._"
        )
        return "\n".join(lines)

    # top player
    preds = payload.get("predictions", [])
    lines = ["**Predicted top fantasy scorers:**"]
    for p in preds:
        lines.append(f"{p['rank']}. {p['team']} — player_id {p['player_id']} "
                      f"({p['predicted_fantasy_points']:.1f} predicted fantasy pts)")
    if payload.get("top_features_for_rank_1"):
        lines.append("Top driver(s) for the #1 pick: " + "; ".join(payload["top_features_for_rank_1"]))
    if not payload.get("used_live_fixture_date"):
        lines.append(
            f"_Note: based on data through {payload['as_of_date']} — no live fixture "
            "calendar available, so this reflects current form, not a confirmed lineup for "
            "a scheduled match._"
        )
    lines.append("_This is a probabilistic model estimate, not a guaranteed outcome._")
    return "\n".join(lines)


def response_formatting_node(state: AgentState) -> dict:
    intent = state.get("intent")
    results = state.get("tool_results", [])

    if intent == "prediction" and state.get("prediction_payload"):
        text = _format_prediction(state["prediction_payload"])
    elif results:
        first = results[0]
        text = first if isinstance(first, str) else str(first)
    else:
        text = state.get("final_response", "I don't have a response for that.")

    return {"final_response": text}