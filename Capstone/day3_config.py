"""Week 7 Day 3 configuration."""

import os

from dotenv import load_dotenv

load_dotenv()


# Groq LLM configuration.
GROQ_MODEL = os.getenv(
    "DAY3_GROQ_MODEL",
    "openai/gpt-oss-20b",
)

GROQ_FALLBACK_MODEL = os.getenv(
    "DAY3_GROQ_FALLBACK_MODEL",
    "openai/gpt-oss-120b",
)


# Deepgram STT configuration.
STT_PROVIDER = os.getenv(
    "STT_PROVIDER",
    "deepgram",
).lower()

DEEPGRAM_API_KEY = os.getenv(
    "DEEPGRAM_API_KEY",
    "",
)

DEEPGRAM_MODEL = os.getenv(
    "DEEPGRAM_MODEL",
    "nova-3",
)

DEEPGRAM_LANGUAGE = os.getenv(
    "DEEPGRAM_LANGUAGE",
    "multi",
)


# Deepgram TTS configuration.
TTS_PROVIDER = os.getenv(
    "TTS_PROVIDER",
    "deepgram",
).lower()

VOICE_MODE = os.getenv("VOICE_MODE", "deepgram").lower()

DEEPGRAM_TTS_MODEL = os.getenv(
    "DEEPGRAM_TTS_MODEL",
    "aura-2-thalia-en",
)

FISH_API_KEY = os.getenv("FISH_API_KEY", "")
FISH_VOICE_ID = os.getenv("FISH_VOICE_ID", "")
FISH_MODEL = os.getenv("FISH_MODEL", "s2-pro")


# Vapi configuration is retained for the existing integration.
VAPI_PUBLIC_KEY = os.getenv("VAPI_PUBLIC_KEY", "")
if VAPI_PUBLIC_KEY.startswith("your_"):
    VAPI_PUBLIC_KEY = ""

VAPI_ASSISTANT_ID = os.getenv("VAPI_ASSISTANT_ID", "")
if VAPI_ASSISTANT_ID.startswith("your_"):
    VAPI_ASSISTANT_ID = ""

VAPI_FIRST_MESSAGE = os.getenv(
    "VAPI_FIRST_MESSAGE",
    "Assalam o alaikum! Main aapki property requirements mein kaise madad kar sakta hoon?",
)


# Memory and evaluation configuration.
MEMORY_DB = os.getenv(
    "DAY3_MEMORY_DB",
    "./day3_memory.db",
)

EVAL_DIR = os.getenv(
    "DAY3_EVAL_DIR",
    "./evaluation_records",
)


# Performance / conversation configuration.
LATENCY_TARGET_MS = int(
    os.getenv("LATENCY_TARGET_MS", "2000")
)

MAX_HISTORY_TURNS = int(
    os.getenv("MAX_HISTORY_TURNS", "12")
)