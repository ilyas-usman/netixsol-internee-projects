"""
run_e2e_tests.py — Week 6 / Day 4 — Task 5
=============================================
Run: python3 run_e2e_tests.py   (needs GROQ_API_KEY in .env)

10+ full conversations exercising every path (factual retrieval,
prediction x2, off-topic refusal, ambiguous->clarification, and a
multi-turn follow-up), plus a full state trace (router decision -> tool
called -> validation -> final response) logged and annotated for 3 of them.
"""
import time
from graph import build_graph, ask

app = build_graph()

# Each entry: (thread_id, [turns]) -- multi-turn threads share a thread_id
# so the router's recent_context and the checkpointer's memory both kick in.
CONVERSATIONS = [
    ("t1-retrieval", ["What were Marcus Bontempelli's stats in round 11, 2025?"]),
    ("t2-prediction-match", ["Who will win Collingwood vs Geelong this week?"]),
    ("t3-prediction-player", ["Who's going to top-score for the Cats this week?"]),
    ("t4-off-topic", ["What's the capital of France?"]),
    ("t5-ambiguous", ["How's Bontempelli going this year?"]),
    ("t6-unsupported-prediction", ["Who's predicted to kick the most goals this week?"]),
    ("t7-unknown-team", ["Who will win Fake Team vs Geelong this week?"]),
    ("t8-not-found-stat", ["What were Fake Player's stats in round 99, 2025?"]),
    ("t9-factual", ["What's a free kick in AFL?"]),
    ("t10-nickname-prediction", ["Who will win the Pies vs the Dogs this week?"]),
    # multi-turn follow-up thread
    ("t11-multiturn", [
        "What's the head-to-head record between the Bulldogs and Carlton?",
        "And who will win if they played this week?",
        "What about the capital of France?",
    ]),
]

TRACE_THREADS = {"t2-prediction-match", "t5-ambiguous", "t11-multiturn"}


def run():
    for thread_id, turns in CONVERSATIONS:
        print(f"\n{'=' * 90}\nTHREAD: {thread_id}\n{'=' * 90}")
        for turn in turns:
            print(f"\nUSER: {turn}")
            result = ask(app, thread_id, turn)
            print(f"AGENT: {result['final_response']}")
            if thread_id in TRACE_THREADS:
                print("  --- state trace ---")
                print(f"  router decision : intent={result.get('intent')} "
                      f"reasoning=\"{result.get('intent_reasoning')}\"")
                print(f"  entities        : {result.get('entities')}")
                print(f"  tool called     : {'yes' if result.get('tool_results') else 'no'} "
                      f"-> {str(result.get('tool_results'))[:200]}")
                print(f"  validation      : status={result.get('validation_status')}")
                print(f"  final_response  : {result['final_response'][:150]}")
            time.sleep(1.2)  # stay under Groq free-tier TPM cap, same pattern as agent.py


if __name__ == "__main__":
    run()
