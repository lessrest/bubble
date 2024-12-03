import os
from datetime import UTC, datetime
from typing import Generator

from starlette.datastructures import URL
from rdflib import XSD, Literal
from fastapi import APIRouter, Request, WebSocket

from bubble.oggw import OggWriter
from bubble.html import HypermediaResponse, tag
from bubble.mint import fresh_id
from bubble.prfx import NT
from bubble.rdfa import rdf_resource
from bubble.repo import using_bubble
from bubble.util import S, new, select_one_row
from bubble.page import action_button, base_html
from bubble.blob import BlobStore

from trio_websocket import open_websocket_url
import trio

import structlog

logger = structlog.get_logger()


class AudioPacketDatabase:
    def __init__(self, db_path: str = "audio_packets.db"):
        self.blob_store = BlobStore(db_path)

    def create_stream(
        self, socket_url: URL, sample_rate: int = 48000, channels: int = 1
    ) -> S:
        """Create a new audio stream and return its ID"""
        timestamp = datetime.now(UTC)

        return new(
            NT.AudioPacketStream,
            {
                NT.wasCreatedAt: Literal(timestamp),
                NT.hasSampleRate: Literal(sample_rate),
                NT.hasChannelCount: Literal(channels),
                NT.hasPacketIngress: new(
                    NT.PacketIngress,
                    {
                        NT.hasWebSocketURI: Literal(
                            socket_url, datatype=XSD.anyURI
                        ),
                        NT.hasPacketType: NT.OpusPacket20ms,
                    },
                ),
            },
        )

    def append_packet(self, src: str, seq: int, dat: bytes):
        """Add a frame to the stream"""
        self.blob_store.append_blob(src, seq, dat)

    def get_frames(
        self, stream_id: str, start_seq: int, end_seq: int
    ) -> Generator[bytes, None, None]:
        """Retrieve frames for a stream starting from sequence number"""
        return self.blob_store.get_blobs(stream_id, start_seq, end_seq)

    def close_stream(self, stream_id: str):
        """Mark a stream as closed"""
        new(
            NT.AudioPacketStream,
            {
                NT.wasClosedAt: Literal(datetime.now(UTC)),
            },
            subject=stream_id,
        )


# FastAPI Router setup
router = APIRouter()


@router.post("/opus")
async def create_stream(
    request: Request,
    sample_rate: int = 48000,
    channels: int = 1,
):
    """Create a new audio stream"""
    audio = AudioPacketDatabase()
    socket_url = generate_socket_url(request)
    stream = audio.create_stream(socket_url, sample_rate, channels)

    rdf_resource(stream)
    return HypermediaResponse()


def generate_socket_url(request: Request) -> URL:
    socket_url = URL(
        scope={
            "scheme": "ws" if request.url.scheme == "http" else "wss",
            "path": f"/opus/{fresh_id()}",
            "server": (request.url.hostname, request.url.port),
            "headers": {},
        },
    )

    return socket_url


@router.get("/opus")
async def get_index():
    """Get the main page"""
    with base_html("Audio Streams"):
        with tag(
            "form",
            method="post",
            hx_post=router.url_path_for("create_stream"),
            hx_swap="outerHTML",
            classes="flex flex-col gap-2 min-h-screen items-start mt-4 mx-2",
        ):
            action_button("New Voice Memo", type="submit")


audiodb = AudioPacketDatabase()


@router.websocket("/opus/{ingress_id}")
async def stream_audio(browser_socket: WebSocket, ingress_id: str):
    """WebSocket endpoint for streaming OPUS frames"""
    await browser_socket.accept()

    with using_bubble(browser_socket.app.state.bubble):
        src = retrieve_websocket_stream(browser_socket)
        logger.info("Stream created", stream=src)

        async with create_deepgram_websocket() as deepgram_socket:
            async with trio.open_nursery() as nursery:

                async def forward_audio_packets():
                    seq = 0
                    while True:
                        dat = await browser_socket.receive_bytes()
                        await deepgram_socket.send_message(dat)
                        audiodb.append_packet(src=src, seq=seq, dat=dat)

                        seq += 1
                        if seq % 100 == 0:
                            logger.info("Added 100 frames", stream=src)

                async def read_transcription_events():
                    while True:
                        frame_data = await deepgram_socket.get_message()
                        logger.info(
                            "Deepgram message", frame_data=frame_data
                        )
                        await browser_socket.send_text(frame_data)

                nursery.start_soon(forward_audio_packets)
                nursery.start_soon(read_transcription_events)

        audiodb.close_stream(src)


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


def retrieve_websocket_stream(websocket):
    return select_one_row(
        """
          SELECT ?stream WHERE {
              ?stream nt:hasPacketIngress ?ingress .
              ?ingress nt:hasWebSocketURI ?endpoint .
          }
          """,
        bindings={"endpoint": Literal(websocket.url, datatype=XSD.anyURI)},
    )[0]


@router.get("/opus/{stream_id}")
async def get_audio_segment(stream_id: str, t0: float, t1: float):
    """Retrieve an audio segment as an OGG file"""
    from io import BytesIO

    from fastapi.responses import Response

    from_seq = int(t0 / 0.02)
    to_seq = int(t1 / 0.02)

    frames = [
        frame for frame in audiodb.get_frames(stream_id, from_seq, to_seq)
    ]

    if not frames:
        return Response(content=b"", media_type="audio/ogg")

    # Create in-memory buffer for OGG file
    buffer = BytesIO()

    # Initialize OGG writer with standard OPUS parameters
    writer = OggWriter(
        stream=buffer,
        sample_rate=48000,  # Standard OPUS sample rate
        channel_count=1,  # Mono audio
        pre_skip=0,
    )

    # Write each frame as an RTP packet
    for i, frame_data in enumerate(frames):
        packet = {"payload": frame_data, "timestamp": (i + 1) * 960}
        writer.write_rtp(packet)

    # Close the writer to finalize the OGG file
    writer.close()

    # Get the buffer contents
    ogg_data = buffer.getvalue()
    buffer.close()

    return Response(
        content=ogg_data,
        media_type="audio/ogg",
        headers={
            "Content-Disposition": f"attachment; filename={stream_id}.ogg"
        },
    )
