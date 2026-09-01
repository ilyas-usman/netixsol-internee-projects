"""Deepgram streaming speech-to-text provider."""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

import websockets
from websockets.exceptions import ConnectionClosedOK

from day3_config import (
    DEEPGRAM_API_KEY,
    DEEPGRAM_MODEL,
    DEEPGRAM_LANGUAGE,
)


async def deepgram_transcripts(
    audio_in: AsyncIterator[bytes],
) -> AsyncIterator[str]:
    """Stream PCM audio to Deepgram and yield final transcripts."""

    if not DEEPGRAM_API_KEY:
        raise RuntimeError(
            "DEEPGRAM_API_KEY is required for streaming STT."
        )

    params = (
        f"model={DEEPGRAM_MODEL}"
        f"&language={DEEPGRAM_LANGUAGE}"
        f"&encoding=linear16"
        f"&sample_rate=16000"
        f"&channels=1"
        f"&interim_results=true"
        f"&smart_format=true"
        f"&punctuate=true"
        f"&endpointing=300"
    )

    url = f"wss://api.deepgram.com/v1/listen?{params}"

    async with websockets.connect(
        url,
        additional_headers={
            "Authorization": f"Token {DEEPGRAM_API_KEY}"
        },
        max_size=None,
    ) as ws:

        async def sender():
            async for audio in audio_in:
                if audio:
                    await ws.send(audio)

            await ws.send(
                json.dumps({"type": "CloseStream"})
            )

        sender_task = asyncio.create_task(sender())

        try:
            while True:
                try:
                    raw = await ws.recv()
                except ConnectionClosedOK:
                    break

                if isinstance(raw, bytes):
                    continue

                message = json.loads(raw)

                if message.get("type") != "Results":
                    if message.get("type") in ("CloseStream", "close"):
                        break
                    continue

                alternatives = (
                    message.get("channel", {})
                    .get("alternatives")
                    or [{}]
                )

                transcript = alternatives[0].get(
                    "transcript",
                    "",
                ).strip()

                if not transcript:
                    continue

                if (
                    message.get("is_final")
                    or message.get("speech_final")
                ):
                    yield transcript

        finally:
            sender_task.cancel()

            try:
                await sender_task
            except asyncio.CancelledError:
                pass