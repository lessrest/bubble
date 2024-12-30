"""NATS-based VAT-to-VAT communication for mesh networking."""

from typing import Any, Callable, Awaitable
import functools
import structlog
import trio_asyncio
from nats.aio.client import Client as NATS


logger = structlog.get_logger(__name__)


class TrioNatsClient:
    """A trio-compatible wrapper around the NATS client."""

    def __init__(self, url: str = "nats://localhost:4222"):
        self.url = url
        self.nc = NATS()

    async def connect(self) -> None:
        """Connect to NATS server."""
        await trio_asyncio.aio_as_trio(self.nc.connect)(self.url)

    async def publish(self, subject: str, payload: bytes) -> None:
        """Publish a message to a subject."""
        await trio_asyncio.aio_as_trio(self.nc.publish)(subject, payload)

    async def subscribe(
        self, subject: str, cb: Callable[[Any], Awaitable[None]]
    ) -> None:
        """Subscribe to a subject with a callback."""

        async def trio_cb(msg):
            await trio_asyncio.aio_as_trio(cb)(msg)

        f = functools.partial(self.nc.subscribe, subject, cb=trio_cb)
        await trio_asyncio.aio_as_trio(f)()

    async def request(
        self, subject: str, payload: bytes, timeout: float = 5.0
    ) -> Any:
        """Make a request and wait for a response."""
        f = functools.partial(
            self.nc.request, subject, payload, timeout=timeout
        )
        return await trio_asyncio.aio_as_trio(f)()

    async def close(self) -> None:
        """Close the connection."""
        await trio_asyncio.aio_as_trio(self.nc.close)()
