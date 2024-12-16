import json
import base64
import pathlib
import ssl
from typing import Optional, AsyncGenerator
import structlog
from dataclasses import dataclass

import trio
import httpx
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from rdflib import Graph, URIRef

from bubble.keys import verify_signed_data
from swash.prfx import NT

logger = structlog.get_logger(__name__)


@dataclass
class Peer:
    """A peer that can connect to a bubble town."""

    private_key: ed25519.Ed25519PrivateKey
    public_key: ed25519.Ed25519PublicKey
    client: Optional[httpx.AsyncClient] = None

    @classmethod
    def generate(cls) -> "Peer":
        """Generate a new peer with a fresh keypair."""
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        return cls(private_key=private_key, public_key=public_key)

    def get_public_key_hex(self) -> str:
        """Get the public key as a hex string."""
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        ).hex()

    def sign(self, data: bytes) -> bytes:
        """Sign data with the peer's private key."""
        return self.private_key.sign(data)

    async def connect(self, town_url: str) -> None:
        """Connect to a town via HTTP."""
        # Ensure URL ends with /
        if not town_url.endswith("/"):
            town_url += "/"

        # Add join endpoint and public key
        join_url = f"{town_url}join/{self.get_public_key_hex()}"

        logger.info("connecting to town", url=join_url)

        try:
            # Setup SSL context
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ssl_context.load_verify_locations(
                cafile=pathlib.Path(__file__).parent.parent.parent
                / "priv/localhost.pem",
            )

            # Create HTTP client
            self.client = httpx.AsyncClient(
                verify=ssl_context,
                headers={"Accept": "application/ld+json"},
                timeout=30.0,
            )

            # Get initial handshake
            async with self.client.stream("GET", join_url) as response:
                response.raise_for_status()
                handshake_msg = await response.aread()
                handshake = Graph()
                handshake.parse(data=handshake_msg, format="json-ld")

                logger.info("received handshake", graph=handshake)

                # Extract and verify the signed question
                for subject in handshake.subjects(None, NT.Handshake):
                    signed_question = handshake.value(
                        subject, NT.signedQuestion
                    )
                    if signed_question:
                        # Sign our response
                        signed_answer = self.sign(b"hello")

                        # Create response graph
                        response = Graph()
                        response.add(
                            (
                                subject,
                                NT.signedAnswer,
                                URIRef(
                                    base64.b64encode(signed_answer).decode()
                                ),
                            )
                        )

                        logger.info("sending response", graph=response)

                        # Send response
                        resp = await self.client.post(
                            join_url,
                            content=response.serialize(format="json-ld"),
                            headers={"Content-Type": "application/ld+json"},
                        )
                        resp.raise_for_status()

                        logger.info("handshake complete")

                        # Start message polling
                        async with trio.open_nursery() as nursery:
                            nursery.start_soon(self._poll_messages, join_url)
                            nursery.start_soon(self._heartbeat, join_url)

        except Exception as e:
            logger.error("connection error", error=e)
            if self.client:
                await self.client.aclose()
            raise

    async def _poll_messages(self, url: str) -> None:
        """Poll for messages from the server."""
        try:
            while True:
                if not self.client:
                    break
                    
                async with self.client.stream("GET", f"{url}/messages") as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            msg_data = line[6:]
                            msg_graph = Graph()
                            msg_graph.parse(data=msg_data, format="json-ld")
                            await self.handle_message(msg_graph)
                
                # Small delay between polls
                await trio.sleep(0.1)
                
        except Exception as e:
            logger.error("polling error", error=e)
            if self.client:
                await self.client.aclose()

    async def _heartbeat(self, url: str) -> None:
        """Send periodic heartbeat messages."""
        try:
            while True:
                if not self.client:
                    break
                    
                await trio.sleep(30)
                await self.client.post(
                    f"{url}/heartbeat",
                    json={"type": "heartbeat"},
                )
        except Exception as e:
            logger.error("heartbeat error", error=e)

    async def handle_message(self, message: Graph) -> None:
        """Handle an incoming message. Override this in subclasses."""
        logger.info("received message", graph=message)

    async def close(self) -> None:
        """Close the connection."""
        if self.client:
            await self.client.aclose()
            self.client = None
