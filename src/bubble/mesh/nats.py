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
        self.connected = False

    async def connect(self) -> None:
        """Connect to NATS server."""
        await trio_asyncio.aio_as_trio(self.nc.connect)(self.url)
        self.connected = True

    async def publish(self, subject: str, payload: bytes) -> None:
        """Publish a message to a subject."""
        if not self.connected:
            await self.connect()
        await trio_asyncio.aio_as_trio(self.nc.publish)(subject, payload)

    async def subscribe(
        self, subject: str, cb: Callable[[Any], Awaitable[None]]
    ) -> None:
        """Subscribe to a subject with a callback."""
        if not self.connected:
            await self.connect()

        async def trio_cb(msg):
            await trio_asyncio.aio_as_trio(cb)(msg)

        f = functools.partial(self.nc.subscribe, subject, cb=trio_cb)
        await trio_asyncio.aio_as_trio(f)()

    async def request(
        self, subject: str, payload: bytes, timeout: float = 5.0
    ) -> Any:
        """Make a request and wait for a response."""
        if not self.connected:
            await self.connect()
        f = functools.partial(
            self.nc.request, subject, payload, timeout=timeout
        )
        return await trio_asyncio.aio_as_trio(f)()

    async def broadcast_actor_message(self, actor_uri: str, message: bytes):
        """Broadcast a message intended for a specific actor."""
        subject = f"bubble.actor.{actor_uri}"
        await self.publish(subject, message)

    async def subscribe_to_actor_messages(
        self, cb: Callable[[str, bytes], Awaitable[None]]
    ):
        """Subscribe to all actor messages."""

        async def wrapper(msg):
            subject = msg.subject
            actor_uri = subject.split("bubble.actor.")[-1]
            await cb(actor_uri, msg.data)

        await self.subscribe("bubble.actor.*", wrapper)

    async def close(self) -> None:
        """Close the connection."""
        if self.connected:
            await trio_asyncio.aio_as_trio(self.nc.close)()
            self.connected = False
