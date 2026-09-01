"""Day 3 streaming pipeline: audio -> STT -> Groq streaming LLM -> streaming TTS."""
from __future__ import annotations
import asyncio, json, re, time
from typing import AsyncIterator, Callable

from groq import Groq
from day3_config import GROQ_MODEL, GROQ_FALLBACK_MODEL
from day3_agent import run_turn
from tts_providers import stream_tts


def _natural_lead_in(transcript: str) -> str:
    """Return a short spoken cue while the grounded answer is prepared."""
    text = transcript.lower()
    if "haha" in text or "lol" in text:
        return "Haha, ji bilkul..."
    if any(word in text for word in ("mehnga", "mehngi", "expensive", "suitable nahi", "concern")):
        return "Hmm, samajh sakta hoon..."
    if "?" in transcript or any(word in text for word in ("options", "kya", "how", "which")):
        return "Ji, ek second sir..."
    return "Acha, ji bilkul..."

def sentence_chunks(tokens: AsyncIterator[str], min_chars=40):
    """Convert token stream to speakable clauses without waiting for the full answer."""
    async def gen():
        buf=""
        async for token in tokens:
            buf += token
            if re.search(r"[.!?؟]\s*$", buf) or len(buf)>=180:
                text=buf.strip()
                if text:
                    yield text+" "
                buf=""
        if buf.strip(): yield buf.strip()+" "
    return gen()

async def groq_stream_text(prompt: str):
    client=Groq()
    def call(model):
        return client.chat.completions.create(
            model=model,
            messages=[
                {"role":"system","content":"You are a concise Pakistani real-estate voice assistant. Speak natural UrduLish. No markdown. Use only supplied grounded facts."},
                {"role":"user","content":prompt},
            ],
            temperature=0.3,
            stream=True,
            max_tokens=220,
        )
    try:
        stream=call(GROQ_MODEL)
    except Exception:
        stream=call(GROQ_FALLBACK_MODEL)
    for chunk in stream:
        delta=chunk.choices[0].delta.content if chunk.choices else None
        if delta: yield delta

async def run_voice_text_turn(session_id: str, transcript: str, send_audio: Callable):
    """Text-to-voice turn used by the UI and as the control path for STT transcripts."""
    started=time.perf_counter()
    result_task = asyncio.create_task(asyncio.to_thread(run_turn, session_id, transcript))
    first_audio_at = None

    async def answer_tokens():
        # Emit a natural cue before the grounded turn finishes, so TTS can start
        # while SQL/RAG/LLM work continues in the background.
        yield _natural_lead_in(transcript)
        result = await result_task
        yield result["response"]

    try:
        async for audio in stream_tts(sentence_chunks(answer_tokens())):
            if first_audio_at is None:
                first_audio_at = time.perf_counter()
            await send_audio(audio)
    except asyncio.CancelledError:
        result_task.cancel()
        raise
    except Exception as exc:
        result = await result_task
        result["tts_error"] = str(exc)
    else:
        result = await result_task
    elapsed=(time.perf_counter()-started)*1000
    result["timings"]["voice_total_ms"]=elapsed
    if first_audio_at is not None:
        result["timings"]["voice_first_audio_ms"]=(first_audio_at-started)*1000
    return result
