import json
import base64
import pathlib
import ssl
from typing import Optional
import structlog
from dataclasses import dataclass

import trio
import trio_websocket
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
        """Connect to a town's websocket endpoint."""
        # Convert http(s):// to ws(s)://
        if town_url.startswith("https://"):
            ws_url = f"wss://{town_url[8:]}"
        elif town_url.startswith("http://"):
            ws_url = f"ws://{town_url[7:]}"
        else:
            ws_url = town_url

        # Ensure URL ends with /
        if not ws_url.endswith("/"):
            ws_url += "/"

        # Add join endpoint and public key
        ws_url += f"join/{self.get_public_key_hex()}"

        logger.info("connecting to town", url=ws_url)

        try:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ssl_context.load_verify_locations(
                cafile=pathlib.Path(__file__).parent.parent.parent
                / "priv/localhost.pem",
            )
            # pudb.set_trace()
            async with trio_websocket.open_websocket_url(
                ws_url,
                ssl_context=ssl_context,
            ) as ws:
                # Receive handshake
                handshake_msg = await ws.get_message()
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
                        await ws.send_message(
                            response.serialize(format="json-ld")
                        )

                        logger.info("handshake complete")

                        # Now enter message loop
                        async with trio.open_nursery() as nursery:
                            nursery.start_soon(self._receive_messages, ws)
                            nursery.start_soon(self._heartbeat, ws)

        except BaseException as e:
            logger.error("websocket error", error=e)
            raise

    async def _receive_messages(
        self, ws: trio_websocket.WebSocketConnection
    ) -> None:
        """Receive and handle messages from the websocket."""
        try:
            while True:
                message = await ws.get_message()
                msg_graph = Graph()
                msg_graph.parse(data=message, format="json-ld")
                await self.handle_message(msg_graph)
        except trio_websocket.ConnectionClosed:
            logger.info("websocket closed")

    async def _heartbeat(
        self, ws: trio_websocket.WebSocketConnection
    ) -> None:
        """Send periodic heartbeat messages."""
        try:
            while True:
                await trio.sleep(30)
                await ws.send_message(json.dumps({"type": "heartbeat"}))
        except trio_websocket.ConnectionClosed:
            pass

    async def handle_message(self, message: Graph) -> None:
        """Handle an incoming message. Override this in subclasses."""
        logger.info("received message", graph=message)
