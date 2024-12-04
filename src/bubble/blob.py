import sqlite3
from typing import Generator
from rdflib import URIRef
import structlog

logger = structlog.get_logger()


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

    def append_blob(self, stream_id: str, seq: int, data: bytes):
        """Add a blob to a stream/collection"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO blobs (stream_id, seq, data) VALUES (?, ?, ?)",
                (stream_id, seq, data),
            )

    def get_blobs(
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
