# Week 5 Day 2 — LangChain: Tools, Chains, Memory & Agents

This notebook rebuilds the Day 1 raw-Python agent using LangChain, then extends it with tools, memory, structured output, and error handling.

## Setup

1. Install dependencies:
   ```
   pip install langchain langchain-groq langchain-core python-dotenv pandas pydantic
   ```
2. Create a `.env` file in the project root with your Groq API key:
   ```
   XAI_API_KEY=your_key_here
   ```
3. Run the notebook cells top to bottom (a kernel restart is recommended before a full run).

## Model

Uses Groq's `llama-3.3-70b-versatile` via `langchain-groq`, with `temperature=0` for consistent output.

## Tasks

**Task 1 — LangChain Setup & Core Concepts**
Maps Day 1's raw-Python agent onto LangChain equivalents (LLM wrapper, tools, agent loop, memory) and builds a basic LCEL chain (`prompt | llm`).

**Task 2 — Define & Register Tools**
Three tools built with the `@tool` decorator: `calculator` (safe AST-based math), `get_weather` (local dataset), and `lookup_product` (reads from a real `products.csv` file).

**Task 3 — Build an Agent**
Agent built with `create_agent` (LangGraph-based) instead of the older `create_tool_calling_agent` + `AgentExecutor`, due to a dependency conflict — noted in-notebook. Includes a multi-step tool-calling trace, annotated with `[ACT]` / `[OBSERVE]` / `[FINAL]` labels.

**Task 4 — Conversation Memory**
Tests `RunnableWithMessageHistory` first, documents why it's incompatible with `create_agent`'s unified message state, then falls back to a manual session-based memory helper for a working 3-turn conversation.

**Task 5 — Structured Output & Error Handling**
Forces the agent's final answer into a `ProductRecommendation` Pydantic schema via `response_format`. Adds a tool that randomly fails and documents how error handling was implemented (manually, inside the tool) after discovering `create_agent` does not catch tool exceptions automatically.

## Known Issue

In Task 3, `for tool in agent_tools:` shadows the imported `tool` decorator from `langchain_core.tools`. A `from langchain_core.tools import tool` re-import guard is added before Task 5 as a workaround; the underlying loop variable should eventually be renamed to `tool_item`.

## Files

- `products.csv` — generated at runtime, acts as the local product database for the `lookup_product` tool.
