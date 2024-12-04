import os

from typing import Generator
from datetime import UTC, datetime

import trio
import structlog

from rdflib import XSD, Literal
from fastapi import Request, APIRouter, WebSocket
from trio_websocket import open_websocket_url
from starlette.datastructures import URL

from bubble.blob import BlobStore
from bubble.html import HypermediaResponse, tag
from bubble.mint import fresh_id
from bubble.oggw import OggWriter, TimedAudioPacket
from bubble.page import base_html, action_button
from bubble.prfx import NT
from bubble.rdfa import rdf_resource
from bubble.repo import using_bubble
from bubble.util import S, new, select_rows, select_one_row

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


audiodb = AudioPacketDatabase()


@router.get("/opus")
async def get_index():
    """Get the main page"""
    with base_html("Audio Streams"):
        with tag(
            "div",
            classes="flex flex-col gap-4 min-h-screen items-start mt-4 mx-2",
        ):
            # Form for creating new stream
            with tag(
                "form",
                method="post",
                hx_post=router.url_path_for("create_stream"),
                hx_swap="outerHTML",
                classes="w-full",
            ):
                action_button("New Voice Memo", type="submit")

            # Get streams with audio packets
            streams_with_packets = (
                audiodb.blob_store.get_streams_with_blobs()
            )

            if streams_with_packets:
                # Get creation times for these streams
                stream_info = select_rows(
                    """
                    SELECT ?stream ?created WHERE {
                        ?stream a nt:AudioPacketStream ;
                               nt:wasCreatedAt ?created .
                    }
                    ORDER BY DESC(?created)
                    """
                )

                logger.info(
                    "Stream info",
                    stream_info=stream_info,
                    streams_with_packets=streams_with_packets,
                )

                with tag("div", classes="w-full"):
                    with tag("ul", classes="space-y-2"):
                        for stream_id, created_str in stream_info:
                            if stream_id not in streams_with_packets:
                                continue

                            rdf_resource(stream_id)


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


@router.get("/opus/{path:path}")
async def get_audio_segment(path: str, t0: float, t1: float):
    """Retrieve an audio segment as an OGG file"""
    from io import BytesIO

    from fastapi.responses import Response

    from_seq = int(t0 / 0.02)
    to_seq = int(t1 / 0.02)

    frames = [frame for frame in audiodb.get_frames(path, from_seq, to_seq)]

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
        packet = TimedAudioPacket(
            payload=frame_data, timestamp=(i + 1) * 960
        )
        writer.write_packet(packet)

    # Close the writer to finalize the OGG file
    writer.close()

    # Get the buffer contents
    ogg_data = buffer.getvalue()
    buffer.close()

    return Response(
        content=ogg_data,
        media_type="audio/ogg",
    )
