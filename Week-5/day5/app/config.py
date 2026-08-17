"""
Central configuration: environment variables and the shared LLM client.
"""
import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError(
        "GROQ_API_KEY is configured"
    )

MODEL_NAME = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
PROJECT_NAME = "Support Ticket Triage Agent"
FRAMEWORK = "LangGraph"
MODEL_PROVIDER = "Groq"

# Set to "true" to auto-approve human-review tickets (used only for
# batch evaluation runs, never for the live API).
EVALUATION_MODE = os.getenv("EVALUATION_MODE", "false").lower() == "true"

llm = ChatGroq(
    api_key=GROQ_API_KEY,
    model=MODEL_NAME,
    temperature=0,
)
