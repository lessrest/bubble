import base64
import pathlib
import ssl
from dataclasses import dataclass
from typing import Optional, AsyncGenerator
from datetime import UTC, datetime

import trio
import httpx
from httpx_ws import aconnect_ws
import structlog
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from rdflib import XSD, Dataset, Graph, Literal, URIRef, RDF

# External namespaces (assuming these are defined in swash.prfx)
from swash.prfx import NT, PROV

logger = structlog.get_logger(__name__)


@dataclass
class Peer:
    """
    A peer that can connect to a Bubble Town service via WebSocket.

    This class:
      - Generates a new Ed25519 keypair for secure identification and signing.
      - Connects to a "town" endpoint over WebSocket (wss://).
      - Handles a handshake process with a signed question/answer exchange.
      - Continuously receives messages from the server and sends heartbeats.
    """

    private_key: ed25519.Ed25519PrivateKey
    public_key: ed25519.Ed25519PublicKey
    ws: Optional[AsyncGenerator] = None

    @classmethod
    def generate(cls) -> "Peer":
        """
        Generate a new peer with a fresh Ed25519 keypair.
        """
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        return cls(private_key=private_key, public_key=public_key)

    def get_public_key_hex(self) -> str:
        """
        Return the public key as a lowercase hex string.
        """
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        ).hex()

    def sign(self, data: bytes) -> bytes:
        """
        Sign the given data with this peer's private key.
        """
        return self.private_key.sign(data)

    async def connect(self, town_url: str) -> None:
        """
        Connect to a town via WebSocket, perform handshake, and start
        message handling and heartbeat loops.

        :param town_url: The HTTPS URL of the town to connect to.
        """
        # Convert HTTP to WebSocket URL
        ws_url = self._convert_to_ws_url(town_url)

        # Construct join endpoint with public key
        join_url = f"{ws_url}join/{self.get_public_key_hex()}"
        logger.info("Connecting to town", url=join_url)

        # Create an SSL context to trust the local CA if necessary
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        cert_path = (
            pathlib.Path(__file__).parent.parent.parent
            / "priv"
            / "localhost.pem"
        )
        ssl_context.load_verify_locations(cafile=cert_path)

        try:
            async with httpx.AsyncClient(verify=False) as client:
                async with aconnect_ws(join_url, client=client) as ws:
                    # Perform the handshake
                    await self._perform_handshake(ws)

                    # Launch concurrent tasks for message handling and heartbeat
                    async with trio.open_nursery() as nursery:
                        nursery.start_soon(self._handle_messages, ws)
                        nursery.start_soon(self._heartbeat, ws)

        except Exception as e:
            logger.error("Connection error", error=e)
            raise

    def _convert_to_ws_url(self, town_url: str) -> str:
        """
        Convert an HTTPS town URL to a WSS URL, ensuring a trailing slash.

        :param town_url: The HTTPS URL of the town.
        :return: The corresponding WSS URL.
        """
        ws_url = town_url.replace("https://", "wss://")
        if not ws_url.endswith("/"):
            ws_url += "/"
        return ws_url

    async def _perform_handshake(self, ws) -> None:
        """
        Perform the initial handshake with the remote town via the WebSocket.

        :param ws: The WebSocket connection.
        """
        # Receive the initial handshake message from the server
        handshake_msg = await ws.receive_text()
        handshake = Graph()
        handshake.parse(data=handshake_msg, format="turtle")
        logger.info("Received handshake", graph=handshake)

        # Locate the handshake subject and extract the signed question
        for subject in handshake.subjects(None, NT.Handshake):
            signed_question = handshake.value(subject, NT.signedQuestion)
            if signed_question:
                # Use the handshake URI itself as the nonce
                nonce_bytes = str(subject).encode()
                
                # Sign our response using the handshake URI as nonce
                signed_answer = self.sign(nonce_bytes)

                # Build a response graph
                response = Graph()
                response.add(
                    (
                        subject,
                        NT.signedAnswer,
                        Literal(
                            base64.b64encode(signed_answer),
                            datatype=XSD.base64Binary,
                        ),
                    )
                )
                logger.info("Sending handshake response", graph=response)

                # Send the response to complete the handshake
                await ws.send_text(response.serialize(format="turtle"))
                logger.info("Handshake complete")

    async def _handle_messages(self, ws) -> None:
        """
        Continuously receive and process messages from the WebSocket.

        :param ws: The WebSocket connection.
        """
        try:
            while True:
                try:
                    message = await ws.receive_text()
                    msg_graph = Dataset()
                    msg_graph.parse(data=message, format="trig")
                    await self.handle_message(msg_graph)
                except Exception as e:
                    logger.error("Message handling error", error=e)
                    break
        except Exception as e:
            logger.error("Message handler terminated", error=e)

    async def _heartbeat(self, ws) -> None:
        """
        Send periodic heartbeat messages to the town.

        :param ws: The WebSocket connection.
        """
        try:
            while True:
                await trio.sleep(5)
                heartbeat = self._create_heartbeat_graph()
                await ws.send_text(heartbeat.serialize(format="trig"))
                logger.info("Sent heartbeat")
        except Exception as e:
            logger.error("Heartbeat error", error=e)

    def _create_heartbeat_graph(self) -> Dataset:
        """
        Create a heartbeat message graph.

        :return: A Dataset containing a heartbeat message.
        """
        heartbeat = Dataset()
        hb_node = URIRef("#heartbeat")
        heartbeat.add((hb_node, RDF.type, NT.Heartbeat))
        heartbeat.add(
            (hb_node, PROV.generatedAtTime, Literal(datetime.now(UTC)))
        )
        return heartbeat

    async def handle_message(self, message: Dataset) -> None:
        """
        Handle an incoming message. Override this method in subclasses
        for custom behavior.

        :param message: An RDF Dataset containing the incoming message.
        """
        logger.info("Received message", graph=message)

        # Check if the dataset contains a heartbeat and log latency if acknowledged
        if heartbeat := message.value(None, RDF.type, NT.Heartbeat):
            t0 = message.value(heartbeat, PROV.generatedAtTime)
            t1 = message.value(heartbeat, NT.acknowledgedAtTime)
            if t0 and t1:
                t0, t1 = t0.toPython(), t1.toPython()
                if isinstance(t0, datetime) and isinstance(t1, datetime):
                    latency = t1 - t0
                    logger.info(
                        "Heartbeat latency", t0=t0, t1=t1, latency=latency
                    )


# Example usage (if running this module directly):
# async def main():
#     peer = Peer.generate()
#     await peer.connect("https://example-town-url.com/")
#
# if __name__ == "__main__":
#     trio.run(main)
