import random
import struct

from enum import IntEnum
from typing import Final, Union, BinaryIO
from pathlib import Path
from dataclasses import dataclass

from bubble.bits import ByteArrayWriter


class PageHeaderType(IntEnum):
    """Enum for OGG page header types."""

    CONTINUATION = 0x00
    BEGINNING = 0x02
    END = 0x04


@dataclass
class TimedAudioPacket:
    """Represents a packet of encoded audio data with a sampletimestamp."""

    timestamp: int
    payload: bytes

    def __post_init__(self):
        if not self.payload:
            raise ValueError("Timed audio packet must have payload")


@dataclass
class OggPage:
    """Represents a single OGG page with header and payload."""

    payload: bytes
    header_type: PageHeaderType
    granule_pos: int
    page_index: int
    serial: int

    def __post_init__(self):
        if not self.payload:
            raise ValueError("Cannot create page with empty payload")

    def serialize(self) -> bytes:
        """Convert the OGG page to bytes format."""
        n_segments = (len(self.payload) // 255) + 1

        writer = (
            ByteArrayWriter()
            .raw(OggWriter.PAGE_HEADER_SIGNATURE)
            .u8(OggWriter.VERSION)
            .u8(self.header_type)
            .u64(self.granule_pos)
            .u32(self.serial)
            .u32(self.page_index)
            .pad(4)  # CRC placeholder
            .u8(n_segments)
        )

        # Segment table
        for _ in range(n_segments - 1):
            writer.u8(255)
        writer.u8(len(self.payload) % 255)

        # Add payload
        writer.raw(self.payload)

        # Calculate and insert checksum
        page_data = bytes(writer)
        checksum = OggWriter.calculate_crc(page_data)
        writer.write_at(22, struct.pack("<I", checksum))

        return bytes(writer)


class OggWriter:
    """
    A class for writing Opus audio data to an OGG container format.

    This implementation follows the OGG bitstream version 0 specification
    and the Opus audio codec specification.
    """

    # Class constants
    PAGE_HEADER_SIGNATURE: Final[bytes] = b"OggS"
    ID_PAGE_SIGNATURE: Final[bytes] = b"OpusHead"
    COMMENT_PAGE_SIGNATURE: Final[bytes] = b"OpusTags"
    PAGE_HEADER_SIZE: Final[int] = 27
    CRC_POLYNOMIAL: Final[int] = 0x104C11DB7
    VERSION: Final[int] = 0

    def __init__(
        self,
        stream: Union[str, Path, BinaryIO],
        sample_rate: int,
        channel_count: int,
        pre_skip: int = 0,
    ) -> None:
        """Initialize the OGG writer."""
        if sample_rate <= 0:
            raise ValueError("Sample rate must be positive")
        if channel_count <= 0:
            raise ValueError("Channel count must be positive")
        if pre_skip < 0:
            raise ValueError("Pre-skip cannot be negative")

        self.sample_rate = sample_rate
        self.channel_count = channel_count
        self.pre_skip = pre_skip
        self.serial = random.randint(0, 2**32 - 1)
        self.page_index = 0

        # Timestamp and Granule MUST start from 1
        # Only headers can have 0 values
        self.previous_timestamp = 1
        self.previous_granule_position = 1
        self.last_payload_size = 0

        self._setup_stream(stream)
        self._write_headers()

    def _setup_stream(self, stream: Union[str, Path, BinaryIO]) -> None:
        """Set up the output stream."""
        self.fd = None
        if isinstance(stream, (str, Path)):
            self.fd = open(stream, "wb")
            self.stream = self.fd
        else:
            self.stream = stream

    @staticmethod
    def calculate_crc(seq: bytes) -> int:
        """Calculate CRC32 checksum for OGG stream."""
        crc = 0
        for b in seq:
            crc ^= b << 24
            for _ in range(8):
                crc = (
                    (crc << 1) ^ OggWriter.CRC_POLYNOMIAL
                    if crc & 0x80000000
                    else crc << 1
                )
        return crc

    def _write_headers(self) -> None:
        """Write ID and comment headers to the stream."""
        # ID Header
        writer = (
            ByteArrayWriter()
            .raw(self.ID_PAGE_SIGNATURE)
            .u8(self.VERSION)
            .u8(self.channel_count)
            .u16(self.pre_skip)
            .u32(self.sample_rate)
            .u16(0)
            .u8(0)
        )

        data = self._create_page(
            bytes(writer), PageHeaderType.BEGINNING, 0, self.page_index
        )
        self._write_to_stream(data)
        self.page_index += 1

        # Comment Header
        writer = ByteArrayWriter()
        vendor = b"bubl"
        (
            writer.raw(self.COMMENT_PAGE_SIGNATURE)  # OpusTags
            .u32(len(vendor))  # Vendor string length
            .raw(vendor)  # Vendor string
            .u32(0)  # User comment list length
            #            .u8(0)  # Additional padding
        )

        data = self._create_page(
            bytes(writer), PageHeaderType.CONTINUATION, 0, self.page_index
        )
        self._write_to_stream(data)
        self.page_index += 1

    def _create_page(
        self,
        payload: bytes,
        header_type: PageHeaderType,
        granule_pos: int,
        page_index: int,
    ) -> bytes:
        """Create an OGG page containing the given payload."""
        page = OggPage(
            payload=payload,
            header_type=header_type,
            granule_pos=granule_pos,
            page_index=page_index,
            serial=self.serial,
        )
        return page.serialize()

    def write_packet(self, packet: TimedAudioPacket) -> None:
        """Write a timed audio payload to the OGG container."""
        # Update granule position
        if self.previous_timestamp != 1:
            increment = packet.timestamp - self.previous_timestamp
            self.previous_granule_position += increment
        else:
            self.previous_granule_position = 961

        self.previous_timestamp = packet.timestamp

        # Create and write page
        data = self._create_page(
            packet.payload,
            PageHeaderType.CONTINUATION,
            self.previous_granule_position,
            self.page_index,
        )
        self._write_to_stream(data)
        self.page_index += 1
        self.last_payload_size = len(packet.payload)

    def _write_to_stream(self, data: bytes) -> None:
        """Write data to the output stream."""
        if not self.stream:
            raise IOError("Stream is closed")
        self.stream.write(data)

    def close(self) -> None:
        """Close the OGG writer and finalize the file."""
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
                    PageHeaderType.END,
                    self.previous_granule_position,
                    self.page_index - 1,
                )

                self._write_to_stream(data)
        finally:
            if self.fd:
                self.fd.close()
                self.fd = None
            self.stream = None


def create_ogg_writer(
    filename: Union[str, Path],
    sample_rate: int,
    channel_count: int,
    pre_skip: int = 0,
) -> OggWriter:
    """Create a new OGG writer with the specified parameters."""
    return OggWriter(filename, sample_rate, channel_count, pre_skip)
