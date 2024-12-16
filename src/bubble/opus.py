import os

import structlog

from fastapi import APIRouter
from trio_websocket import open_websocket_url

from swash.html import tag
from swash.prfx import NT
from swash.rdfa import rdf_resource
from swash.util import select_rows
from bubble.data import context
from bubble.page import base_html, action_button

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
            streams_with_packets = list(
                context.repo.get().get_streams_with_blobs()
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
