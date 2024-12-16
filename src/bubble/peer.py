import json
import base64
import pathlib
import ssl
from typing import Optional, AsyncGenerator
import structlog
from dataclasses import dataclass

import trio
import httpx
from httpx_ws import aconnect_ws
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from rdflib import Graph, URIRef, RDF

from bubble.keys import verify_signed_data
from swash.prfx import NT

logger = structlog.get_logger(__name__)


@dataclass
class Peer:
    """A peer that can connect to a bubble town."""

    private_key: ed25519.Ed25519PrivateKey
    public_key: ed25519.Ed25519PublicKey
    ws: Optional[AsyncGenerator] = None

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
        """Connect to a town via WebSocket."""
        # Convert HTTP URL to WebSocket URL
        ws_url = town_url.replace("https://", "wss://")
        if not ws_url.endswith("/"):
            ws_url += "/"

        # Add join endpoint and public key
        join_url = f"{ws_url}join/{self.get_public_key_hex()}"

        logger.info("connecting to town", url=join_url)

        try:
            # Setup SSL context
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ssl_context.load_verify_locations(
                cafile=pathlib.Path(__file__).parent.parent.parent
                / "priv/localhost.pem",
            )

            # Create WebSocket connection using httpx-ws
            async with httpx.AsyncClient() as client:
                async with aconnect_ws(join_url, client=client, verify=ssl_context) as ws:
                    self.ws = ws
                    
                    # Receive initial handshake
                    handshake_msg = await self.ws.receive_text()
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
                    await self.ws.send_text(
                        response.serialize(format="json-ld")
                    )

                    logger.info("handshake complete")

                    # Start message handling loop
                    async with trio.open_nursery() as nursery:
                        nursery.start_soon(self._handle_messages)
                        nursery.start_soon(self._heartbeat)

        except Exception as e:
            logger.error("connection error", error=e)
            if self.ws:
                await self.ws.close()
            raise

    async def _handle_messages(self) -> None:
        """Handle incoming WebSocket messages."""
        try:
            while self.ws:
                try:
                    message = await self.ws.receive_text()
                    msg_graph = Graph()
                    msg_graph.parse(data=message, format="json-ld")
                    await self.handle_message(msg_graph)
                except Exception as e:
                    logger.error("message handling error", error=e)
                    break

        finally:
            if self.ws:
                await self.ws.close()

    async def _heartbeat(self) -> None:
        """Send periodic heartbeat messages."""
        try:
            while self.ws:
                await trio.sleep(30)
                heartbeat = Graph()
                heartbeat.add((URIRef("#heartbeat"), RDF.type, NT.Heartbeat))
                await self.ws.send_text(
                    heartbeat.serialize(format="json-ld")
                )
        except Exception as e:
            logger.error("heartbeat error", error=e)

    async def handle_message(self, message: Graph) -> None:
        """Handle an incoming message. Override this in subclasses."""
        logger.info("received message", graph=message)

    async def close(self) -> None:
        """Close the WebSocket connection."""
        if self.ws:
            await self.ws.close()
            self.ws = None
