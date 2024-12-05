import os

import structlog

from rdflib import URIRef
from fastapi import APIRouter
from trio_websocket import open_websocket_url

from bubble.html import tag
from bubble.oggw import OggWriter, TimedAudioPacket
from bubble.page import base_html, action_button
from bubble.prfx import NT
from bubble.rdfa import rdf_resource
from bubble.repo import current_bubble
from bubble.util import select_rows

logger = structlog.get_logger()

router = APIRouter()


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
                hx_post="/blob",
                hx_swap="outerHTML",
                classes="w-full",
            ):
                with tag(
                    "input",
                    name="type",
                    type="hidden",
                    value=str(NT.OpusPacket20ms),
                ):
                    pass
                action_button("New Audio Stream", type="submit")

            # Get streams with audio packets
            streams_with_packets = (
                current_bubble.get().get_streams_with_blobs()
            )

            if streams_with_packets:
                # Get creation times for these streams
                stream_info = select_rows(
                    """
                    SELECT ?stream ?created WHERE {
                        ?stream a nt:DataStream ;
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

                with tag("ul", classes="space-y-2"):
                    for stream_id, created_str in stream_info:
                        if stream_id not in streams_with_packets:
                            continue

                        rdf_resource(stream_id)


@router.get("/opus/{path:path}")
async def get_audio_segment(path: str, t0: float, t1: float):
    """Retrieve an audio segment as an OGG file"""
    from io import BytesIO

    from fastapi.responses import Response

    from_seq = int(t0 / 0.02)
    to_seq = int(t1 / 0.02)

    stream = current_bubble.get().blob(URIRef(path))
    frames = stream[from_seq:to_seq]

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
