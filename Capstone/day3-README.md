# Week 7 — Day 3: Voice Agent & Natural Conversation

Day 3 is implemented directly on top of the Day 2 project. Day 2 remains the source of truth for structured SQL facts, ChromaDB RAG, recommendation logic and hallucination controls.

## Architecture

```text
Phone / Browser Audio
        │
        ▼
Deepgram Nova-3 (streaming STT, Urdu/English code-switching)
        │ final transcript
        ▼
LangGraph conversation graph
  ├─ Router + slot extraction
  ├─ Persistent memory (SQLite)
  ├─ SQL retrieval ───────────────┐
  ├─ ChromaDB RAG ────────────────┤
  ├─ Objection detection/strategy│
  └─ Grounded response generation┘
        │
        ▼
Groq GPT-OSS 20B (fast) / 120B fallback
        │ streamed clauses
        ▼
Fish Audio streaming TTS (default)
        │
        ▼
Audio chunks → caller/browser
```

## What was added

### Task 1 — Streaming Voice Pipeline
- FastAPI `/ws/voice/{session_id}` WebSocket.
- Text mode is available even without STT/TTS keys.
- Deepgram Nova-3 adapter supports streaming PCM input and final transcripts.
- Groq uses a low-latency `openai/gpt-oss-20b` default with `openai/gpt-oss-120b` fallback.
- Fish Audio WebSocket TTS streams audio chunks.
- ElevenLabs adapter is optional.
- Per-turn latency metrics are recorded.
- **Important:** the <2 second requirement is a target, not a guarantee; real phone latency depends on STT endpointing, model, TTS, network and audio buffering. The harness measures it.

### Task 2 — Natural Speech
- UrduLish persona.
- Controlled acknowledgements/fillers.
- Concise spoken responses.
- WebSocket interruption command cancels the active response.
- Voice turns emit streamed acknowledgement, hesitation, thinking-pause and laughter cues before the grounded answer when appropriate.

### Task 3 — Context Memory + Router
Persistent SQLite state stores:
- budget
- city/location
- bedrooms
- purpose
- property type
- last shown properties
- objection counters
- recent turns

The router selects:
- `sql` for exact property facts
- `rag` for FAQs/payment/developer prose
- `both` when both are required
- `chat` for small talk

Example:
1. `Budget 3 crore hai.` → `budget=30000000`
2. `DHA mein kya options hain?` → remembers budget + searches SQL
3. `Us se sasti koi option?` → uses last shown prices and searches below them

### Task 4 — Objection Handling
Six categories:
1. price
2. trust
3. location
4. investment
5. builder
6. maintenance

There are 30 labeled examples (5/category). Strategies explicitly tell the agent to ground objections in Day 2 SQL/RAG data and escalate after two unresolved objections on the same category.

### Task 5 — Human Evaluation
`evaluation_harness.py` records:
- transcript
- response
- per-stage latency
- under-2-second flag
- optional audio
- human scores

Score each full call from 1–5 on:
- Naturalness
- Persuasiveness
- Fluency
- Latency
- Conversation flow

## Setup

```powershell
pip install -r requirements-day3.txt
copy .env.example .env
```

Put your real keys in `.env`. Do **not** commit `.env`.

For the preferred stack:

```text
GROQ_API_KEY=...
DEEPGRAM_API_KEY=...
FISH_API_KEY=...
FISH_VOICE_ID=...
```

### Vapi browser voice

Vapi handles microphone capture, STT and TTS in the browser UI. Set these in `cap/.env`:

```text
STT_PROVIDER=vapi
TTS_PROVIDER=vapi
VAPI_PUBLIC_KEY=your_vapi_public_key
VAPI_ASSISTANT_ID=your_vapi_assistant_id
```

In the Vapi dashboard, configure the assistant transcriber for Urdu/English input and its voice provider for the desired UrduLish voice. Only the Vapi public key belongs in browser configuration; never expose a Vapi private/server key.

### Connect Vapi to verified property search

Import `vapi_property_tool.json` in Vapi Dashboard -> Tools, or create a Function tool with the same fields. Set its server URL to:

```text
https://YOUR_PUBLIC_DOMAIN/api/vapi/property-search
```

Attach `property_search` to the assistant. For local testing, Vapi needs a public HTTPS tunnel such as an ngrok URL; `http://127.0.0.1:8001` is not reachable from Vapi's servers. Tell the assistant to call `property_search` for every property search, price, location, bedroom, commercial, or cheaper-alternative request and use only its result.

### Deepgram STT + Fish Audio TTS

The browser UI uses the FastAPI WebSocket for Deepgram streaming STT and Fish Audio TTS. It sends mono 16 kHz linear PCM to Deepgram STT and receives streamed MP3 audio from Fish Audio. Set these in `cap/.env`:

```text
STT_PROVIDER=deepgram
DEEPGRAM_MODEL=nova-3
DEEPGRAM_LANGUAGE=en
TTS_PROVIDER=fish
FISH_API_KEY=your_fish_api_key
FISH_VOICE_ID=your_fish_reference_id
FISH_MODEL=s2-pro
```

`FISH_VOICE_ID` is required by Fish Audio for a selected/cloned reference voice. The GUI displays a clear TTS error if it is missing or the Fish account has no API credit.

### Vapi voice mode

Set `VOICE_MODE=vapi` with `VAPI_PUBLIC_KEY` and `VAPI_ASSISTANT_ID` in `cap/.env`. In the Vapi assistant dashboard select Deepgram as the transcriber and configure the desired voice provider for TTS. Vapi does not provide a standalone TTS engine; it orchestrates the voice provider configured on the assistant. The existing Deepgram WebSocket remains the fallback when Vapi is not configured.

If you only have Groq right now, use the `/api/chat` endpoint first. It exercises the full Day 3 memory/router/objection system without requiring voice credentials.

## Run

```powershell
python -m uvicorn app_day3:app --reload --port 8000
```

Then:
- `GET /health`
- `POST /api/chat`
- `GET /api/memory/{session_id}`
- `DELETE /api/memory/{session_id}`
- `GET /api/evaluation/objections`
- `POST /api/evaluation/score`
- `WS /ws/voice/{session_id}`

### Example text test

```json
POST /api/chat
{
  "session_id": "demo-001",
  "message": "Budget 3 crore hai."
}
```

Then:

```json
{
  "session_id": "demo-001",
  "message": "DHA mein kya options hain?"
}
```

Then:

```json
{
  "session_id": "demo-001",
  "message": "Us se sasti koi option?"
}
```

Inspect memory:

```text
GET /api/memory/demo-001
```

You should see the budget and the last shown SQL properties persisted across turns.

## Tests

```powershell
python test_day3.py
```

The tests cover:
- Pakistani money parsing
- slot extraction
- SQL/RAG/both routing
- all 30 objection cases
- persistent conversation memory

## Day 2 compatibility

No Day 2 source files were replaced. Day 3 imports:
- `structured_retrieval.py`
- `rag_pipeline.py`
- `recommendation_engine.py`
- `knowledge_docs/`
- existing `realestate.db`
- existing ChromaDB

The Day 2 grounding contract remains the authority: the LLM must not invent prices, availability, bedrooms, payment terms or other unsupported property facts.

## Production path after Day 3

For real phone calls, add a telephony ingress such as Twilio Media Streams or a SIP provider in front of `/ws/voice`, then forward caller PCM to Deepgram and return TTS audio in the provider's required codec. Google Calendar/Gmail/Resend, PostgreSQL migration, n8n workflows and deployment are later integration layers; they are intentionally not fabricated into Day 3 because today's tasks are voice, memory, objections and evaluation.
