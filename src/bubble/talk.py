from datetime import UTC, datetime
import os

from typing import List, Optional

from rdflib import Literal, URIRef
import structlog

from pydantic import Field, BaseModel
import trio
from trio_websocket import open_websocket_url


from swash.prfx import NT
from bubble.repo import BubbleRepo, save_bubble
from swash.util import new

logger = structlog.get_logger()


class ModelInfo(BaseModel):
    name: str
    version: str
    arch: str


class Metadata(BaseModel):
    request_id: str
    model_info: ModelInfo
    model_uuid: str


class Word(BaseModel):
    word: str
    start: float
    end: float
    confidence: float
    speaker: int
    punctuated_word: str


class Alternative(BaseModel):
    transcript: str
    confidence: float
    words: List[Word]


class Channel(BaseModel):
    alternatives: List[Alternative]


class DeepgramMessage(BaseModel):
    type: str
    channel_index: List[int]
    duration: float
    start: float
    is_final: bool
    speech_final: bool
    channel: Channel
    metadata: Metadata
    from_finalize: bool = Field(default=False)


class DeepgramParams(BaseModel):
    model: str = "nova-2"
    encoding: Optional[str] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    language: str = "en-US"
    interim_results: bool = True
    punctuate: bool = True
    diarize: bool = True


def using_deepgram_live_session(params: DeepgramParams):
    """Create a websocket connection to Deepgram's streaming API"""
    query_params = []

    query_params.append(f"model={params.model}")
    if params.encoding is not None:
        query_params.append(f"encoding={params.encoding}")
    if params.sample_rate is not None:
        query_params.append(f"sample_rate={params.sample_rate}")
    if params.channels is not None:
        query_params.append(f"channels={params.channels}")
    query_params.append(f"language={params.language}")
    query_params.append(
        f"interim_results={str(params.interim_results).lower()}"
    )
    query_params.append(f"punctuate={str(params.punctuate).lower()}")
    query_params.append(f"diarize={str(params.diarize).lower()}")

    url = "wss://api.deepgram.com/v1/listen?" + "&".join(query_params)

    logger.info("Connecting to Deepgram", url=url)

    headers = [("Authorization", f"Token {os.environ['DEEPGRAM_API_KEY']}")]

    return open_websocket_url(url, extra_headers=headers)


async def handle_websocket_voice_ingress(
    websocket, stream: URIRef, bubble: BubbleRepo
):
    logger.info("Stream created", stream=stream)

    try:
        blob_writer = bubble.blob(stream, seq=0)

        async with using_deepgram_live_session() as deepgram_session:

            async def receive_audio_packets():
                while True:
                    dat = await websocket.receive_bytes()
                    blob_writer.write(dat)
                    await deepgram_session.send_message(dat)

            async def receive_deepgram_messages():
                while True:
                    payload = await deepgram_session.get_message()
                    logger.info("Deepgram message", payload=payload)
                    await websocket.send_text(payload)

                    message = DeepgramMessage.model_validate_json(payload)
                    if message.is_final:
                        if (
                            len(message.channel.alternatives) > 0
                            and message.channel.alternatives[0].transcript
                        ):
                            logger.info(
                                "Final transcription", message=message
                            )
                            transcription = new(
                                NT.Transcription,
                                {
                                    NT.hasOffset: Literal(message.start),
                                    NT.hasDuration: Literal(
                                        message.duration
                                    ),
                                    NT.hasText: Literal(
                                        message.channel.alternatives[
                                            0
                                        ].transcript
                                    ),
                                },
                            )
                            bubble.graph.add(
                                (stream, NT.hasPart, transcription)
                            )
                            await save_bubble()

            async with trio.open_nursery() as nursery:
                nursery.start_soon(receive_audio_packets)
                nursery.start_soon(receive_deepgram_messages)

    finally:
        bubble.graph.add(
            (stream, NT.wasClosedAt, Literal(datetime.now(UTC)))
        )
        await save_bubble()
