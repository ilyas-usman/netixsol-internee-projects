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