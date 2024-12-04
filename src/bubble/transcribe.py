import os
from datetime import UTC, datetime
import trio
import structlog
from rdflib import XSD, URIRef, Literal
from fastapi import APIRouter, WebSocket
from trio_websocket import open_websocket_url

from bubble.prfx import NT
from bubble.repo import using_bubble
from bubble.util import new, select_one_row

logger = structlog.get_logger()

router = APIRouter()


@router.websocket("/transcribe/{stream_id}")
async def transcribe_stream(websocket: WebSocket, stream_id: str):
    """WebSocket endpoint for transcribing a stream"""
    await websocket.accept()

    with using_bubble(websocket.app.state.bubble) as bubble:
        src = URIRef(stream_id)
        logger.info("Starting transcription", stream=src)

        # Verify this is an Opus stream
        stream_type = select_one_row(
            """
            SELECT ?type WHERE {
                ?stream nt:hasPacketType ?type .
            }
            """,
            bindings={"stream": src},
        )[0]

        if stream_type != NT.OpusPacket20ms:
            await websocket.close(code=4000, reason="Not an Opus stream")
            return

        try:
            async with create_deepgram_websocket() as deepgram_socket:
                async with trio.open_nursery() as nursery:

                    async def forward_audio_packets():
                        stream = bubble.blob(src)
                        last_seq = -1
                        while True:
                            current_seq = stream.get_last_sequence()
                            if current_seq > last_seq:
                                for seq in range(
                                    last_seq + 1, current_seq + 1
                                ):
                                    dat = stream[seq]
                                    await deepgram_socket.send_message(dat)
                                last_seq = current_seq
                            await trio.sleep(
                                0.01
                            )  # Small delay to prevent busy loop

                    async def read_transcription_events():
                        while True:
                            frame_data = await deepgram_socket.get_message()
                            logger.info(
                                "Deepgram message", frame_data=frame_data
                            )
                            await websocket.send_text(frame_data)

                    nursery.start_soon(forward_audio_packets)
                    nursery.start_soon(read_transcription_events)
        finally:
            new(
                NT.TranscriptionSession,
                {
                    NT.wasClosedAt: Literal(datetime.now(UTC)),
                },
                subject=src,
            )


def create_deepgram_websocket():
    """Create a websocket connection to Deepgram's streaming API"""
    url = (
        "wss://api.deepgram.com/v1/listen?"
        "model=nova-2&"
        "encoding=opus&"
        "sample_rate=48000&"
        "channels=1&"
        "language=en-US&"
        "interim_results=true&"
        "punctuate=true&"
        "diarize=true"
    )

    headers = [("Authorization", f"Token {os.environ['DEEPGRAM_API_KEY']}")]

    return open_websocket_url(url, extra_headers=headers)
