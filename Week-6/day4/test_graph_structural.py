"""
test_graph_structural.py
=========================
NOT part of the Day-4 deliverable itself -- this is a sandbox-only sanity
check, run here because this environment has no GROQ_API_KEY / no network
access to Groq. It monkeypatches router.classify_intent (and the factual
node's LLM call) with fixed IntentClassification objects, so the actual
graph structure, retrieval-tool dispatch, prediction wrappers, validation
branching, and clarification loop can all be exercised against your REAL
data/models with zero guessing.

Run test_router.py and run_e2e_tests.py for real (LLM-driven) accuracy
numbers once you have a .env with GROQ_API_KEY on your own machine -- this
file's job is only to prove the graph itself is wired correctly.
"""
import router
import graph_nodes
from router import IntentClassification
import graph

# -- stub the router's LLM call -------------------------------------------
_SCRIPT = {
    "What were Marcus Bontempelli's stats in round 11, 2025?": IntentClassification(
        intent="retrieval", reasoning="asks for a past stat line",
        retrieval_tool="get_player_round_stats", player_name="Marcus Bontempelli",
        season=2025, round_number="11",
    ),
    "Who will win Collingwood vs Geelong this week?": IntentClassification(
        intent="prediction", reasoning="future match outcome",
        prediction_type="match_winner", team_a="Collingwood", team_b="Geelong", date_hint="this week",
    ),
    "Who will win Pies vs Cats this week?": IntentClassification(
        intent="prediction", reasoning="future match outcome, nicknames",
        prediction_type="match_winner", team_a="Pies", team_b="Cats", date_hint="this week",
    ),
    "Who's going to top-score for the Cats this week?": IntentClassification(
        intent="prediction", reasoning="future top scorer",
        prediction_type="top_player", team_a="Cats", date_hint="this week",
    ),
    "Who will kick the most goals this week?": IntentClassification(
        intent="prediction", reasoning="unmodeled stat type",
        prediction_type="other_unsupported",
    ),
    "What's the capital of France?": IntentClassification(
        intent="off_topic", reasoning="not AFL related",
    ),
    "What's a free kick in AFL?": IntentClassification(
        intent="factual", reasoning="rules question, no number needed",
    ),
    "Who will win Nonexistent Team vs Geelong this week?": IntentClassification(
        intent="prediction", reasoning="future match outcome, bad team name",
        prediction_type="match_winner", team_a="Nonexistent Team", team_b="Geelong", date_hint="this week",
    ),
    "What were Fake Player's stats in round 99, 2025?": IntentClassification(
        intent="retrieval", reasoning="past stat line, likely missing",
        retrieval_tool="get_player_round_stats", player_name="Fake Player",
        season=2025, round_number="99",
    ),
    "How's Bontempelli going this year?": IntentClassification(
        intent="retrieval", reasoning="ambiguous stat request, no stat/season resolved",
        retrieval_tool="get_player_season_average", player_name="Bontempelli",
        season=None, stat="disposals",
    ),
}


def _stub_classify_intent(user_query, recent_context="", max_retries=4):
    if user_query in _SCRIPT:
        return _SCRIPT[user_query]
    return IntentClassification(intent="off_topic", reasoning="not in test script")


def _stub_factual_node(state):
    return {"tool_results": ["A free kick is awarded for a rules infringement and allows an unimpeded kick or handball."],
            "validation_status": "ok"}


router.classify_intent = _stub_classify_intent
graph_nodes.factual_node = _stub_factual_node

# router_node in graph.py was imported by reference before we patched --
# rebuild the graph AFTER patching so it picks up the stub.
import importlib
importlib.reload(router)
router.classify_intent = _stub_classify_intent
import graph as graph_module
importlib.reload(graph_module)
# graph_module.router_node references router.classify_intent internally via
# router.router_node -> re-patch after reload
import router as router_mod
router_mod.classify_intent = _stub_classify_intent


def run():
    app = graph_module.build_graph()
    # patch the node function actually registered in the compiled graph:
    # easiest reliable path is to re-patch classify_intent right before use,
    # which we've done above (router_node calls classify_intent by name
    # lookup at call time inside the router module).
    graph_module.graph_nodes = graph_nodes
    from graph_nodes import factual_node as _fn  # noqa (already stubbed)

    thread = "structural-test-thread"
    turns = list(_SCRIPT.keys())
    for t in turns:
        print(f"\nUSER: {t}")
        r = graph_module.ask(app, thread, t)
        print(f"  intent={r.get('intent')}  validation_status={r.get('validation_status')}")
        print(f"  AGENT: {r['final_response']}")


if __name__ == "__main__":
    run()
