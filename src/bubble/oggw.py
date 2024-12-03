from dataclasses import dataclass
import random
import struct
from typing import BinaryIO


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
