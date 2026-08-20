from graph import build_graph, ask

def run():
    print("AFL Router Runtime Tester")
    print("Type 'exit' or 'quit' to stop.\n")

    app = build_graph()
    thread_id = "runtime-chat"

    while True:
        query = input("Enter your prompt: ").strip()

        if query.lower() in {"exit", "quit"}:
            print("Exiting...")
            break

        if not query:
            print("Please enter a prompt.\n")
            continue

        try:
            response = ask(app, thread_id, query)

            print("\nClassification:")
            print(f"  Intent:           {response.get('intent')}")
            print(f"  Prediction type:  {response.get('entities', {}).get('prediction_type')}")

            print("\nAgent response:")
            print(response["final_response"])
            print()

        except Exception as error:
            print(f"\nError: {error}\n")


if __name__ == "__main__":
    run()