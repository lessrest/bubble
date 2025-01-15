"""Audio File Upload and Whisper Transcription Actor"""

import os
from typing import Dict, Any, cast
from datetime import UTC, datetime

import openai
from rdflib import URIRef, Literal, Namespace

from swash import mint
from swash.prfx import NT
from swash.util import add, new
from bubble.mesh.base import (
    send,
    receive,
    txgraph,
    with_transient_graph,
)

AUDIO = Namespace("https://swa.sh/2024/audio#")


async def whisper_transcribe_actor(actor_uri: URIRef):
    """Actor that handles audio file uploads and transcription."""
    while True:
        msg = await receive()

        file_data = msg.value(predicate=NT.file)
        if not file_data:
            continue

        content = file_data.value(NT.data)
        mime_type = file_data.value(NT.mimeType)

        if not content or not mime_type:
            continue

        temp_path = f"/tmp/{mint.fresh_id()}"
        with open(temp_path, "wb") as f:
            f.write(content)

        try:
            client = openai.AsyncOpenAI()
            with open(temp_path, "rb") as audio_file:
                response = await client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                )
                transcript = cast(Dict[str, Any], response)

            async with txgraph():
                audio_file = new(
                    AUDIO.AudioFile,
                    {
                        NT.mimeType: Literal(mime_type),
                        NT.data: Literal(content),
                    },
                )

                transcription = new(
                    AUDIO.Transcription,
                    {
                        AUDIO.text: Literal(transcript["text"]),
                        AUDIO.sourceFile: audio_file,
                        AUDIO.model: Literal("whisper-1"),
                        AUDIO.timestamp: Literal(datetime.now(UTC)),
                    },
                )

                segments = transcript.get("segments", [])
                for idx, segment in enumerate(segments):
                    seg = new(
                        AUDIO.Segment,
                        {
                            AUDIO.text: Literal(segment["text"]),
                            AUDIO.start: Literal(segment["start"]),
                            AUDIO.end: Literal(segment["end"]),
                            AUDIO.confidence: Literal(
                                segment["confidence"]
                            ),
                            AUDIO["index"]: Literal(idx),
                        },
                    )
                    add(transcription, {AUDIO["hasSegment"]: seg})

                await send(actor_uri)

        finally:
            os.remove(temp_path)


def create_whisper_actor():
    """Create a new Whisper transcription actor."""
    with with_transient_graph() as g:
        actor = mint.fresh_uri(NT)
        new(
            NT.Actor,
            {
                NT.affordance: new(
                    NT.FileUpload,
                    {
                        NT.label: Literal("Upload Audio for Transcription"),
                        NT.accept: Literal("audio/*"),
                        NT.target: actor,
                    },
                )
            },
            subject=actor,
        )
        return actor, g
