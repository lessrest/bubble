import os
import random
import struct
import sqlite3

from typing import Union, BinaryIO, Optional, Generator
from datetime import UTC, datetime
from dataclasses import dataclass

from starlette.datastructures import URL
from rdflib import XSD, Literal
from fastapi import APIRouter, Request, WebSocket

from bubble.html import HypermediaResponse, tag, text
from bubble.mint import fresh_id
from bubble.prfx import NT
from bubble.rdfa import rdf_resource
from bubble.repo import using_bubble
from bubble.util import S, new, select_one_row
from bubble.base_html import base_html

import structlog

logger = structlog.get_logger()


@dataclass
class OpusPacket:
    payload: bytes

    @classmethod
    def unmarshal(cls, data: bytes) -> tuple["OpusPacket", None]:
        return cls(payload=data), None


class OggWriter:
    PAGE_HEADER_TYPE_CONTINUATION = 0x00
    PAGE_HEADER_TYPE_BEGINNING = 0x02
    PAGE_HEADER_TYPE_END = 0x04

    ID_PAGE_SIGNATURE = b"OpusHead"
    COMMENT_PAGE_SIGNATURE = b"OpusTags"
    PAGE_HEADER_SIGNATURE = b"OggS"
    PAGE_HEADER_SIZE = 27

    def __init__(
        self,
        stream: Union[str, BinaryIO],
        sample_rate: int,
        channel_count: int,
        pre_skip: int,
    ):
        self.sample_rate = sample_rate
        self.channel_count = channel_count
        self.pre_skip = pre_skip
        self.serial = random.randint(0, 2**32 - 1)
        self.page_index = 0
        self.checksum_table = self._generate_checksum_table()

        # Timestamp and Granule MUST start from 1
        # Only headers can have 0 values
        self.previous_timestamp = 1
        self.previous_granule_position = 1
        self.last_payload_size = 0

        # Handle file/stream opening
        self.fd = None
        if isinstance(stream, str):
            self.fd = open(stream, "wb")
            self.stream = self.fd
        else:
            self.stream = stream

        # Write initial headers
        self._write_headers()

    def _generate_checksum_table(self) -> list[int]:
        table = []
        poly = 0x04C11DB7

        for i in range(256):
            r = i << 24
            for _ in range(8):
                if (r & 0x80000000) != 0:
                    r = ((r << 1) ^ poly) & 0xFFFFFFFF
                else:
                    r = (r << 1) & 0xFFFFFFFF
                table.append(r & 0xFFFFFFFF)
        return table

    def _create_page(
        self,
        payload: bytes,
        header_type: int,
        granule_pos: int,
        page_index: int,
    ) -> bytes:
        self.last_payload_size = len(payload)
        n_segments = (len(payload) // 255) + 1

        # Create page header
        header = bytearray()
        header.extend(self.PAGE_HEADER_SIGNATURE)  # 'OggS'
        header.append(0)  # Version
        header.append(header_type)
        header.extend(struct.pack("<Q", granule_pos))  # granule position
        header.extend(struct.pack("<I", self.serial))  # serial
        header.extend(struct.pack("<I", page_index))  # page sequence number
        header.extend(b"\x00\x00\x00\x00")  # checksum (placeholder)
        header.append(n_segments)  # number of segments

        # Segment table
        for i in range(n_segments - 1):
            header.append(255)
        header.append(len(payload) % 255)

        # Combine header and payload
        page = header + payload

        # Calculate checksum
        checksum = 0
        for byte in page:
            checksum = (
                (checksum << 8)
                ^ self.checksum_table[(checksum >> 24) & 0xFF ^ byte]
            ) & 0xFFFFFFFF

        # Insert checksum
        struct.pack_into("<I", page, 22, checksum)

        return page

    def _write_headers(self):
        # ID Header
        id_header = bytearray()
        id_header.extend(self.ID_PAGE_SIGNATURE)  # OpusHead
        id_header.append(1)  # Version
        id_header.append(self.channel_count)
        id_header.extend(struct.pack("<H", self.pre_skip))  # pre-skip
        id_header.extend(struct.pack("<I", self.sample_rate))  # sample rate
        id_header.extend(struct.pack("<H", 0))  # output gain
        id_header.append(0)  # channel map

        data = self._create_page(
            id_header, self.PAGE_HEADER_TYPE_BEGINNING, 0, self.page_index
        )
        self._write_to_stream(data)
        self.page_index += 1

        # Comment Header
        comment_header = bytearray()
        comment_header.extend(self.COMMENT_PAGE_SIGNATURE)  # OpusTags
        comment_header.extend(struct.pack("<I", 5))  # Vendor Length
        comment_header.extend(b"pion")  # Vendor name
        comment_header.extend(
            struct.pack("<I", 0)
        )  # User Comment List Length

        data = self._create_page(
            comment_header,
            self.PAGE_HEADER_TYPE_CONTINUATION,
            0,
            self.page_index,
        )
        self._write_to_stream(data)
        self.page_index += 1

    def write_rtp(self, packet: Optional[dict]) -> None:
        """Write an RTP packet to the OGG container"""
        if packet is None:
            raise ValueError("Invalid nil packet")

        payload = packet.get("payload")
        if not payload:
            return

        # Parse opus packet
        opus_packet = OpusPacket.unmarshal(payload)[0]
        payload = opus_packet.payload

        # Update granule position
        if self.previous_timestamp != 1:
            increment = packet["timestamp"] - self.previous_timestamp
            self.previous_granule_position += increment
        else:
            self.previous_granule_position = 961

        self.previous_timestamp = packet["timestamp"]

        # Create and write page
        data = self._create_page(
            payload,
            self.PAGE_HEADER_TYPE_CONTINUATION,
            self.previous_granule_position,
            self.page_index,
        )
        self.page_index += 1
        self._write_to_stream(data)

    def _write_to_stream(self, data: bytes) -> None:
        if not self.stream:
            raise IOError("File not opened")
        self.stream.write(data)

    def close(self) -> None:
        """Close the OGG writer and finalize the file"""
        try:
            if self.fd:
                # Seek back one page to update header
                self.fd.seek(
                    -1
                    * (self.last_payload_size + self.PAGE_HEADER_SIZE + 1),
                    2,
                )

                # Read the last payload
                payload = self.fd.read()[self.PAGE_HEADER_SIZE + 1 :]

                # Create final page with END flag
                data = self._create_page(
                    payload,
                    self.PAGE_HEADER_TYPE_END,
                    self.previous_granule_position,
                    self.page_index - 1,
                )

                # Write final page
                self._write_to_stream(data)
        finally:
            if self.fd:
                self.fd.close()
                self.fd = None
            self.stream = None


def create_ogg_writer(
    filename: str, sample_rate: int, channel_count: int, pre_skip: int = 0
) -> OggWriter:
    """Helper function to create a new OGG writer"""
    return OggWriter(filename, sample_rate, channel_count, pre_skip)


class AudioStreamManager:
    def __init__(self, db_path: str = "audio_packets.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the SQLite database with minimal schema"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS packets (
                    src TEXT NOT NULL,    -- Stream source ID
                    seq INTEGER NOT NULL, -- Sequence number
                    dat BLOB NOT NULL,    -- Raw packet data
                    PRIMARY KEY (src, seq)
                )
            """)

    def create_stream(
        self, socket_url: URL, sample_rate: int = 48000, channels: int = 1
    ) -> S:
        """Create a new audio stream and return its ID"""
        timestamp = datetime.now(UTC)
        ingress = new(
            NT.PacketIngress,
            {
                NT.hasWebSocketURI: Literal(
                    socket_url, datatype=XSD.anyURI
                ),
                NT.hasPacketType: NT.OpusPacket20ms,
            },
        )

        # Create RDF entity for the stream
        return new(
            NT.AudioPacketStream,
            {
                NT.wasCreatedAt: Literal(timestamp),
                NT.hasSampleRate: Literal(sample_rate),
                NT.hasChannelCount: Literal(channels),
                NT.hasPacketIngress: ingress,
            },
        )

    def add_frame(
        self, stream_id: str, sequence_number: int, frame_data: bytes
    ):
        """Add a frame to the stream"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO packets (src, seq, dat) VALUES (?, ?, ?)",
                (stream_id, sequence_number, frame_data),
            )

    def get_frames(
        self, stream_id: str, start_seq: int, end_seq: int
    ) -> Generator[bytes, None, None]:
        """Retrieve frames for a stream starting from sequence number"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT dat FROM packets WHERE src = ? AND seq >= ? AND seq <= ? ORDER BY seq",
                (stream_id, start_seq, end_seq),
            )
            for (frame_data,) in cursor:
                yield frame_data

    def close_stream(self, stream_id: str):
        """Mark a stream as closed"""
        # Update RDF to mark stream as ended
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
    audio_manager = AudioStreamManager()
    socket_url = URL(
        scope={
            "scheme": "ws" if request.url.scheme == "http" else "wss",
            "path": f"/opus/{fresh_id()}",
            "server": (request.url.hostname, request.url.port),
            "headers": {},
        },
    )

    stream = audio_manager.create_stream(socket_url, sample_rate, channels)

    rdf_resource(stream)
    return HypermediaResponse()


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
            with tag(
                "button",
                type="submit",
                classes=[
                    "relative inline-flex flex-row gap-2 justify-center items-center align-middle",
                    "px-2 py-1",
                    "border border-gray-300 text-center",
                    "shadow-md shadow-slate-300 dark:shadow-slate-800/50",
                    "hover:border-gray-400 hover:bg-gray-50",
                    "focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:border-indigo-500",
                    "active:bg-gray-100 active:border-gray-500",
                    "transition-colors duration-150 ease-in-out",
                    "dark:border-slate-900 dark:bg-slate-900/50",
                    "dark:hover:bg-slate-900 dark:hover:border-slate-800",
                    "dark:focus:ring-indigo-600 dark:focus:border-indigo-600",
                    "dark:active:bg-slate-800 dark:text-slate-200",
                ],
            ):
                # with tag("voice-recorder-writer"):
                #     pass
                with tag(
                    "span",
                    classes="font-medium",
                ):
                    text("New Voice Memo")


@router.websocket("/opus/{ingress_id}")
async def stream_audio(websocket: WebSocket, ingress_id: str):
    """WebSocket endpoint for streaming OPUS frames"""
    await websocket.accept()

    audio_manager = AudioStreamManager()

    with using_bubble(websocket.app.state.bubble):
        stream = select_one_row(
            """
          SELECT ?stream WHERE {
              ?stream nt:hasPacketIngress ?ingress .
              ?ingress nt:hasWebSocketURI ?endpoint .
          }
          """,
            bindings={
                "endpoint": Literal(websocket.url, datatype=XSD.anyURI)
            },
        )[0]

        logger.info("Stream created", stream=stream)

        from trio_websocket import open_websocket_url
        import trio

        async with open_websocket_url(
            "wss://api.deepgram.com/v1/listen?model=nova-2&encoding=opus&sample_rate=48000&channels=1&language=en-US&interim_results=true&punctuate=true&diarize=true",
            extra_headers=[
                (
                    "Authorization",
                    f"Token {os.environ['DEEPGRAM_API_KEY']}",
                )
            ],
        ) as ws:
            async with trio.open_nursery() as nursery:

                async def receiver():
                    sequence_number = 0
                    while True:
                        frame_data = await websocket.receive_bytes()
                        await ws.send_message(frame_data)

                        audio_manager.add_frame(
                            stream_id=stream,
                            sequence_number=sequence_number,
                            frame_data=frame_data,
                        )

                        sequence_number += 1
                        if sequence_number % 100 == 0:
                            logger.info("Added 100 frames", stream=stream)

                async def deepgram_receiver():
                    while True:
                        frame_data = await ws.get_message()
                        logger.info(
                            "Deepgram message", frame_data=frame_data
                        )
                        await websocket.send_text(frame_data)

                nursery.start_soon(receiver)
                nursery.start_soon(deepgram_receiver)

        audio_manager.close_stream(stream)


@router.get("/opus/{stream_id}")
async def get_audio_segment(stream_id: str, t0: float, t1: float):
    """Retrieve an audio segment as an OGG file"""
    from io import BytesIO

    from fastapi.responses import Response

    # 20ms per packet
    # turn second into packet count
    # 1 packet is 20ms
    # 1 packet is 0.02s
    # t0 / 0.02 = from_seq
    # t1 / 0.02 = to_seq

    from_seq = int(t0 / 0.02)
    to_seq = int(t1 / 0.02)

    audio_manager = AudioStreamManager()
    frames = [
        frame
        for frame in audio_manager.get_frames(stream_id, from_seq, to_seq)
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
