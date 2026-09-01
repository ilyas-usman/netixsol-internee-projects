"""Deepgram streaming TTS provider."""

from __future__ import annotations

import asyncio
import json
import urllib.request
from typing import AsyncIterator

from deepgram import DeepgramClient

from day3_config import (
    DEEPGRAM_API_KEY,
    DEEPGRAM_TTS_MODEL,
    FISH_API_KEY,
    FISH_VOICE_ID,
    FISH_MODEL,
    TTS_PROVIDER,
)


async def fish_tts(text_chunks: AsyncIterator[str]) -> AsyncIterator[bytes]:
    """Stream Fish Audio MP3 output for a configured reference voice."""
    if not FISH_API_KEY:
        raise RuntimeError("FISH_API_KEY is required for Fish Audio TTS.")
    if not FISH_VOICE_ID:
        raise RuntimeError("FISH_VOICE_ID is required for Fish Audio TTS.")

    text_parts = []
    async for chunk in text_chunks:
        if chunk.strip():
            text_parts.append(chunk)
    if not text_parts:
        return

    payload = json.dumps({
        "text": " ".join(text_parts),
        "reference_id": FISH_VOICE_ID,
        "model": FISH_MODEL,
        "format": "mp3",
        "latency": "normal",
    }).encode("utf-8")

    def request_audio():
        request = urllib.request.Request(
            "https://api.fish.audio/v1/tts",
            data=payload,
            headers={
                "Authorization": f"Bearer {FISH_API_KEY}",
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            method="POST",
        )
        return urllib.request.urlopen(request, timeout=30)

    response = await asyncio.to_thread(request_audio)
    try:
        while True:
            chunk = await asyncio.to_thread(response.read, 16 * 1024)
            if not chunk:
                break
            yield chunk
    finally:
        response.close()


async def deepgram_tts(
    text_chunks: AsyncIterator[str],
) -> AsyncIterator[bytes]:
    """Generate Deepgram Aura PCM audio without removed SDK websocket symbols."""

    if not DEEPGRAM_API_KEY:
        raise RuntimeError(
            "DEEPGRAM_API_KEY is required for Deepgram TTS."
        )

    text_parts = []
    async for chunk in text_chunks:
        if chunk.strip():
            text_parts.append(chunk)

    if not text_parts:
        return

    client = DeepgramClient(api_key=DEEPGRAM_API_KEY)

    def generate_audio():
        return client.speak.v1.audio.generate(
            text=" ".join(text_parts),
            model=DEEPGRAM_TTS_MODEL,
            encoding="linear16",
            sample_rate=16000,
        )

    audio_response = await asyncio.to_thread(generate_audio)
    for chunk in audio_response:
        if chunk:
            yield bytes(chunk)


async def stream_tts(
    text_chunks: AsyncIterator[str],
) -> AsyncIterator[bytes]:
    """Unified TTS interface."""

    provider = TTS_PROVIDER
    if provider == "fish":
        text_parts = [chunk async for chunk in text_chunks if chunk.strip()]

        async def replay_text():
            for chunk in text_parts:
                yield chunk

        try:
            async for audio in fish_tts(replay_text()):
                yield audio
        except Exception as fish_error:
            # Keep the voice turn usable when Fish credits or account access
            # are unavailable; Deepgram remains a lower-fidelity fallback.
            async for audio in deepgram_tts(replay_text()):
                yield audio
    else:
        async for audio in deepgram_tts(text_chunks):
            yield audio