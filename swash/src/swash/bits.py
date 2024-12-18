import struct

from enum import IntEnum
from typing import Union
from dataclasses import dataclass


class Endian(IntEnum):
    LITTLE = 0
    BIG = 1
    NATIVE = 2


@dataclass
class ByteArrayWriter:
    """A wrapper around bytearray for easier binary writing."""

    _data: bytearray
    _endian: Endian = Endian.LITTLE

    def __init__(self, endian: Endian = Endian.LITTLE):
        self._data = bytearray()
        self._endian = endian

    def __bytes__(self) -> bytes:
        return bytes(self._data)

    def __len__(self) -> int:
        return len(self._data)

    @property
    def data(self) -> bytearray:
        return self._data

    def _get_format(self, fmt: str) -> str:
        """Get format string with proper endianness."""
        if self._endian == Endian.LITTLE:
            return "<" + fmt
        elif self._endian == Endian.BIG:
            return ">" + fmt
        return fmt

    def raw(self, data: Union[bytes, bytearray]) -> "ByteArrayWriter":
        """Write raw bytes."""
        self._data.extend(data)
        return self

    def u8(self, value: int) -> "ByteArrayWriter":
        """Write unsigned 8-bit integer."""
        self._data.append(value & 0xFF)
        return self

    def u16(self, value: int) -> "ByteArrayWriter":
        """Write unsigned 16-bit integer."""
        self._data.extend(struct.pack(self._get_format("H"), value))
        return self

    def u32(self, value: int) -> "ByteArrayWriter":
        """Write unsigned 32-bit integer."""
        self._data.extend(struct.pack(self._get_format("I"), value))
        return self

    def u64(self, value: int) -> "ByteArrayWriter":
        """Write unsigned 64-bit integer."""
        self._data.extend(struct.pack(self._get_format("Q"), value))
        return self

    def string(
        self, value: str, encoding: str = "utf-8"
    ) -> "ByteArrayWriter":
        """Write string with specified encoding."""
        self._data.extend(value.encode(encoding))
        return self

    def pad(self, count: int, value: int = 0) -> "ByteArrayWriter":
        """Add padding bytes."""
        self._data.extend([value] * count)
        return self

    def align(
        self, alignment: int, pad_value: int = 0
    ) -> "ByteArrayWriter":
        """Align to specified byte boundary."""
        remainder = len(self._data) % alignment
        if remainder:
            padding = alignment - remainder
            self.pad(padding, pad_value)
        return self

    def write_at(
        self, offset: int, data: Union[bytes, bytearray]
    ) -> "ByteArrayWriter":
        """Write data at specific offset."""
        if offset + len(data) > len(self._data):
            raise ValueError("Write would extend beyond current size")
        self._data[offset : offset + len(data)] = data
        return self

    def clear(self) -> "ByteArrayWriter":
        """Clear all data."""
        self._data.clear()
        return self
