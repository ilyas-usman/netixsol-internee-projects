"""
chat_interactive.py — Manually type AFL questions at runtime.

This does NOT redefine the agent, tools, or grounding check — it imports
everything from agent.py (build_agent, ask, ToolCallLogger) so there's a
single source of truth. If you tweak SYSTEM_PROMPT or the retrieval tools
in agent.py, this script picks the changes up automatically.

Setup (same as agent.py):
    1. .env file in this folder with GROQ_API_KEY=gsk_your-actual-key-here
    2. pip install -r requirements.txt
    3. Make sure your dataset is in ./dataset (or set AFL_DATA_DIR)

Run:
    python chat_interactive.py

Commands (type these instead of a question):
    /new       start a fresh conversation thread (clears memory)
    /thread    show the current thread id
    /log       print all tool outputs collected so far this session
    /quit, quit, /exit, exit   exit
"""

import uuid

from agent import ToolCallLogger, ask, build_agent


def new_thread_id() -> str:
    return f"afl-chat-{uuid.uuid4().hex[:8]}"


def main():
    print("Building agent (this loads the model + tools once)...")
    agent = build_agent()
    logger = ToolCallLogger()
    thread_id = new_thread_id()

    print("\nAFL Chat Agent — interactive mode.")
    print(f"Thread: {thread_id}")
    print("Type an AFL question, or /quit to exit, /new for a fresh thread, /log to see tool calls.\n")

    while True:
        try:
            user_input = input("USER: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not user_input:
            continue

        if user_input.lower() in ("/quit", "/exit", "quit", "exit"):
            print("Exiting.")
            break

        if user_input.lower() == "/new":
            thread_id = new_thread_id()
            logger.reset()
            print(f"Started a new thread: {thread_id} (memory cleared)\n")
            continue

        if user_input.lower() == "/thread":
            print(f"Current thread: {thread_id}\n")
            continue

        if user_input.lower() == "/log":
            if not logger.calls:
                print("(no tool calls logged yet this session)\n")
            else:
                print("--- Tool outputs logged so far ---")
                for i, call in enumerate(logger.calls, 1):
                    print(f"[{i}] {call}")
                print("-----------------------------------\n")
            continue

        answer = ask(agent, thread_id, user_input, logger)
        print(f"AGENT: {answer}\n")


if __name__ == "__main__":
    main()