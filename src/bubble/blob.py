import sqlite3

from typing import Generator, overload
from datetime import UTC, datetime
from dataclasses import dataclass

import structlog

from rdflib import XSD, URIRef, Literal
from fastapi import Request
from starlette.datastructures import URL

from bubble.mint import fresh_id
from bubble.prfx import NT
from bubble.util import new, select_one_row

logger = structlog.get_logger()


async def create_stream(
    request: Request,
    type: URIRef,
) -> URIRef:
    """Create a new data stream with specified type and upload capability"""
    socket_url = generate_socket_url(request)
    timestamp = datetime.now(UTC)

    stream = new(
        NT.DataStream,
        {
            NT.wasCreatedAt: Literal(timestamp),
            NT.hasPart: new(
                NT.UploadCapability,
                {
                    NT.hasPacketType: type,
                },
                subject=socket_url,
            ),
        },
    )

    return stream


def generate_socket_url(request: Request) -> URIRef:
    socket_url = URL(
        scope={
            "scheme": "ws" if request.url.scheme == "http" else "wss",
            "path": f"/{fresh_id()}",
            "server": (request.url.hostname, request.url.port),
            "headers": {},
        },
    )
    return URIRef(str(socket_url))


@dataclass
class BlobStream:
    """A stream of binary data blobs"""

    blob_store: "BlobStore"
    stream_id: URIRef

    def append_part(self, seq: int, data: bytes):
        """Add a part to the stream"""
        self.blob_store.append_blob(str(self.stream_id), seq, data)

    def get_parts(self, start_seq: int, end_seq: int):
        """Get parts from the stream within a sequence range"""
        return self.blob_store.get_parts(
            str(self.stream_id), start_seq, end_seq
        )

    def get_last_sequence(self) -> int:
        """Get the last sequence number for the stream"""
        return self.blob_store.get_last_sequence(str(self.stream_id))

    def delete(self):
        """Delete all parts in this stream"""
        self.blob_store.delete_stream(str(self.stream_id))

    @overload
    def __getitem__(self, key: int) -> bytes: ...

    @overload
    def __getitem__(self, key: slice) -> Generator[bytes, None, None]: ...

    def __getitem__(self, key):
        """Support slice syntax for getting parts"""
        if isinstance(key, slice):
            start = key.start if key.start is not None else 0
            stop = (
                key.stop
                if key.stop is not None
                else self.get_last_sequence() + 1
            )
            if key.step is not None:
                raise ValueError(
                    "Step is not supported in blob stream slicing"
                )
            return self.get_parts(start, stop)
        else:
            return list(self.get_parts(key, key + 1))[0]


class BlobStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or "blobs.db"
        self._init_db()

    def _init_db(self):
        """Initialize the SQLite database with minimal schema"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS blobs (
                    stream_id TEXT NOT NULL,  -- Stream/collection identifier
                    seq INTEGER NOT NULL,     -- Sequence number/position
                    data BLOB NOT NULL,       -- Raw blob data
                    PRIMARY KEY (stream_id, seq)
                )
            """)

    def stream(self, stream_id: URIRef) -> BlobStream:
        """Get a stream by ID"""
        return BlobStream(self, stream_id)

    def append_blob(self, stream_id: str, seq: int, data: bytes):
        """Add a blob to a stream/collection"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO blobs (stream_id, seq, data) VALUES (?, ?, ?)",
                (stream_id, seq, data),
            )

    def get_parts(
        self, stream_id: str, start_seq: int, end_seq: int
    ) -> Generator[bytes, None, None]:
        """Retrieve blobs from a stream/collection within a sequence range"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT data FROM blobs WHERE stream_id = ? AND seq >= ? AND seq <= ? ORDER BY seq",
                (stream_id, start_seq, end_seq),
            )
            for (blob_data,) in cursor:
                yield blob_data

    def get_last_sequence(self, stream_id: str) -> int:
        """Get the last sequence number for a stream"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT MAX(seq) FROM blobs WHERE stream_id = ?",
                (stream_id,),
            )
            result = cursor.fetchone()[0]
            return result if result is not None else -1

    def get_streams_with_blobs(self) -> list[URIRef]:
        """Get list of stream IDs that have blobs stored"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT DISTINCT stream_id FROM blobs")
            return [URIRef(row[0]) for row in cursor.fetchall()]

    def delete_stream(self, stream_id: str):
        """Delete all blobs for a given stream"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM blobs WHERE stream_id = ?", (stream_id,)
            )
