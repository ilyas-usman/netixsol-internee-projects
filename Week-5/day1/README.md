#### Week 5 Day 1 – Agent Foundations

Built a minimal AI agent from scratch in raw Python. No LangChain, no LangGraph, no CrewAI — wanted to actually understand what's happening under those frameworks first.

#### API Used

Was supposed to use Anthropic API but didn't have access. Tried Gemini next, got blocked because the Google Cloud project had no billing set up. Ended up using Groq (llama-3.3-70b-versatile) through their OpenAI-compatible API instead. Architecture stayed the same, just swapped the provider.

##### What I Built
Chatbot vs Workflow vs Agent — basic mental model of the difference
ReAct loop — Reason → Act → Observe → Repeat
Two tools: calculator (safe, AST-based, no eval()) and get_weather (local dataset lookup)
Tool registry — available_tools dict so I'm not writing if/elif for every tool
run_agent() — the actual loop: sends messages to the model, checks if it wants a tool, runs it, sends the result back, repeats until it gives a final answer
Conversation memory (messages) vs Working memory (state) — what the model needs vs what the app tracks
max_iterations safeguard so it can't loop forever
Breaking It on Purpose
Test	What happened
Ambiguous weather question	Model guessed a city, tool-call broke, caught by try/except
Faisalabad (no data)	Agent said it couldn't get the data instead of making something up
Asked it to "send an email" (no email tool)	Worst one — it just wrote the email as text and never said it couldn't actually send it. No error logged at all
Bad calculator input	AST whitelist blocked it cleanly, no crash
max_iterations=1	Got both cities' weather but got cut off before comparing them

##### Takeaway

Frameworks like LangChain don't do anything conceptually different from this — they just wrap the same loop with more safety nets (retries, loop detection, memory, etc). Building it raw first made that stuff make sense instead of being a black box.