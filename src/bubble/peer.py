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

from bubble.connect import anonymous_connection, signed_connection
from swash.prfx import NT, PROV

logger = structlog.get_logger(__name__)


@dataclass
class Peer:
    """
    A peer that can connect to a Bubble Town service via WebSocket.
    
    This class represents an established connection to a town,
    either with a signed identity or anonymously.
    """
    ws: AsyncGenerator  # The WebSocket connection
    actor_uri: URIRef  # The peer's identity URI in the town

    @classmethod
    async def connect_anonymous(cls, town_url: str) -> "Peer":
        """Connect to a town anonymously via WebSocket."""
        ws_url = convert_to_ws_url(town_url)
        async with anonymous_connection(ws_url) as (ws, actor_uri):
            return cls(ws=ws, actor_uri=actor_uri)

    @classmethod
    async def connect_with_identity(cls, town_url: str) -> "Peer":
        """Connect to a town with a signed identity via WebSocket."""
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        ws_url = convert_to_ws_url(town_url)
        async with signed_connection(ws_url, private_key, public_key) as (ws, actor_uri):
            return cls(ws=ws, actor_uri=actor_uri)

async def establish_anonymous_connection(town_url: str) -> tuple[AsyncGenerator, URIRef]:
    """
    Establish an anonymous connection to a town.
    
    Args:
        town_url: The HTTPS URL of the town to connect to.
    
    Returns:
        A tuple of (websocket, actor_uri) for the established connection.
    """
    ws_url = convert_to_ws_url(town_url)
    join_url = f"{ws_url}join"
    logger.info("Connecting anonymously to town", url=join_url)

    try:
        async with httpx.AsyncClient(verify=False) as client:
            async with aconnect_ws(join_url, client=client) as ws:
                # Receive the handshake with our temporary identity
                handshake_msg = await ws.receive_text()
                handshake = Graph()
                handshake.parse(data=handshake_msg, format="turtle")
                logger.info("Received anonymous handshake", graph=handshake)

                # Extract our assigned actor URI and verify protocol version
                for subject in handshake.subjects(RDF.type, NT.AnonymousHandshake):
                    if handshake.value(subject, NT.protocol) != NT.Protocol_1:
                        raise ValueError("Unsupported protocol version")
                    
                    actor_uri = handshake.value(subject, NT.actor)
                    if not actor_uri:
                        raise ValueError("No actor URI in handshake")

                    # Send acknowledgment
                    ack = Graph()
                    ack.add((subject, NT.acknowledged, Literal(True)))
                    await ws.send_text(ack.serialize(format="turtle"))
                    logger.info("Sent handshake acknowledgment")
                    break
                else:
                    raise ValueError("Invalid handshake message")

                # Launch concurrent tasks for message handling and heartbeat
                async with trio.open_nursery() as nursery:
                    nursery.start_soon(handle_messages, ws)
                    nursery.start_soon(heartbeat, ws)

                return ws, actor_uri

    except Exception as e:
        logger.error("Connection error", error=e)
        raise

async def establish_signed_connection(
    town_url: str,
    private_key: ed25519.Ed25519PrivateKey,
    public_key: ed25519.Ed25519PublicKey,
) -> tuple[AsyncGenerator, URIRef]:
    """
    Establish a signed connection to a town.
    
    Args:
        town_url: The HTTPS URL of the town to connect to.
        private_key: The Ed25519 private key for signing.
        public_key: The corresponding public key.
    
    Returns:
        A tuple of (websocket, actor_uri) for the established connection.
    """
    ws_url = convert_to_ws_url(town_url)
    public_key_hex = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()
    
    join_url = f"{ws_url}join/{public_key_hex}"
    logger.info("Connecting to town with identity", url=join_url)

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
                actor_uri = await perform_handshake(ws, private_key)

                # Launch concurrent tasks for message handling and heartbeat
                async with trio.open_nursery() as nursery:
                    nursery.start_soon(handle_messages, ws)
                    nursery.start_soon(heartbeat, ws)

                return ws, actor_uri

    except Exception as e:
        logger.error("Connection error", error=e)
        raise

def convert_to_ws_url(town_url: str) -> str:
    """Convert an HTTPS town URL to a WSS URL, ensuring a trailing slash."""
    ws_url = town_url.replace("https://", "wss://")
    if not ws_url.endswith("/"):
        ws_url += "/"
    return ws_url

async def perform_handshake(
    ws,
    private_key: ed25519.Ed25519PrivateKey,
) -> URIRef:
    """
    Perform the initial handshake with the remote town via the WebSocket.
    Returns the actor URI assigned by the town.
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
            signed_answer = private_key.sign(nonce_bytes)

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
            
            # Return the actor URI from the handshake
            actor_uri = handshake.value(subject, NT.actor)
            if not actor_uri:
                raise ValueError("No actor URI in handshake response")
            return actor_uri

    raise ValueError("Invalid handshake message")

async def handle_messages(ws) -> None:
    """Continuously receive and process messages from the WebSocket."""
    try:
        while True:
            try:
                message = await ws.receive_text()
                msg_graph = Dataset()
                msg_graph.parse(data=message, format="trig")
                await process_message(msg_graph)
            except Exception as e:
                logger.error("Message handling error", error=e)
                break
    except Exception as e:
        logger.error("Message handler terminated", error=e)

async def heartbeat(ws) -> None:
    """Send periodic heartbeat messages to the town."""
    try:
        while True:
            await trio.sleep(5)
            heartbeat = create_heartbeat_graph()
            await ws.send_text(heartbeat.serialize(format="trig"))
            logger.info("Sent heartbeat")
    except Exception as e:
        logger.error("Heartbeat error", error=e)

def create_heartbeat_graph() -> Dataset:
    """Create a heartbeat message graph."""
    heartbeat = Dataset()
    hb_node = URIRef("#heartbeat")
    heartbeat.add((hb_node, RDF.type, NT.Heartbeat))
    heartbeat.add(
        (hb_node, PROV.generatedAtTime, Literal(datetime.now(UTC)))
    )
    return heartbeat

async def process_message(message: Dataset) -> None:
    """Process an incoming message."""
    logger.info("Received message", graph=message)

    # Check if the dataset contains a heartbeat and log latency if acknowledged
    if heartbeat := message.value(None, RDF.type, NT.Heartbeat):
        t0 = message.value(heartbeat, PROV.generatedAtTime)
        t1 = message.value(heartbeat, NT.acknowledgedAtTime)
        if t0 and t1:
            t0, t1 = t0.toPython(), t1.toPython()
            if isinstance(t0, datetime) and isinstance(t1, datetime):
                t2 = datetime.now(UTC)
                latency = t1 - t0
                roundtrip = t2 - t0
                logger.info(
                    "Heartbeat latency",
                    latency=latency,
                    roundtrip=roundtrip,
                )


# Example usage (if running this module directly):
# async def main():
#     peer = Peer.generate()
#     await peer.connect("https://example-town-url.com/")
#
# if __name__ == "__main__":
#     trio.run(main)
