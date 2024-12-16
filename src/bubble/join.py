import base64

from typing import Tuple, AsyncGenerator
from datetime import UTC, datetime
from contextlib import asynccontextmanager

from swash.util import S
import trio
import httpx
import structlog

from rdflib import RDF, XSD, Dataset, Graph, URIRef, Literal
from fastapi import WebSocket
from httpx_ws import aconnect_ws
from cryptography.hazmat.primitives.asymmetric import ed25519

from swash.prfx import NT, PROV

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def anonymous_connection(
    ws_url: str,
) -> AsyncGenerator[Tuple[WebSocket, URIRef], None]:
    """
    Context manager for establishing an anonymous WebSocket connection to a town.

    Args:
        ws_url: The WebSocket URL of the town to connect to.

    Yields:
        A tuple of (websocket, actor_uri) for the established connection.
    """
    async with httpx.AsyncClient(verify=False) as client:
        async with aconnect_ws(f"{ws_url}join", client=client) as ws:
            # Receive the handshake with our temporary identity
            handshake_msg = await ws.receive_text()
            handshake = Graph()
            handshake.parse(data=handshake_msg, format="turtle")
            logger.info("Received anonymous handshake", graph=handshake)

            # Extract our assigned actor URI and verify protocol version
            for subject in handshake.subjects(
                RDF.type, NT.AnonymousHandshake
            ):
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
                assert isinstance(actor_uri, URIRef)
                yield ws, actor_uri
                return

            raise ValueError("Invalid handshake message")


@asynccontextmanager
async def signed_connection(
    ws_url: str,
    private_key: ed25519.Ed25519PrivateKey,
    public_key: ed25519.Ed25519PublicKey,
) -> AsyncGenerator[Tuple[WebSocket, URIRef], None]:
    """
    Context manager for establishing a signed WebSocket connection to a town.

    Args:
        ws_url: The WebSocket URL of the town to connect to.
        private_key: The Ed25519 private key for signing.
        public_key: The corresponding public key.

    Yields:
        A tuple of (websocket, actor_uri) for the established connection.
    """
    public_key_hex = public_key.public_bytes_raw().hex()

    join_url = f"{ws_url}join/{public_key_hex}"
    logger.info("Connecting to town with identity", url=join_url)

    async with httpx.AsyncClient(verify=False) as client:
        async with aconnect_ws(join_url, client=client) as ws:
            # Receive the initial handshake message
            handshake_msg = await ws.receive_text()
            handshake = Graph()
            handshake.parse(data=handshake_msg, format="turtle")
            logger.info("Received handshake", graph=handshake)

            # Locate the handshake subject and extract the signed question
            for subject in handshake.subjects(RDF.type, NT.Handshake):
                # Use the handshake URI itself as the nonce
                nonce_bytes = str(subject).encode()

                # Sign our response using the nonce
                signed_answer = private_key.sign(nonce_bytes)

                # Build and send response graph
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
                await ws.send_text(response.serialize(format="turtle"))

                # Extract actor URI from handshake
                actor_uri = handshake.value(subject, NT.actor)
                if not actor_uri:
                    raise ValueError("No actor URI in handshake response")

                assert isinstance(actor_uri, URIRef)
                yield ws, actor_uri
                return

            raise ValueError("Invalid handshake message")


async def messages(ws: WebSocket) -> AsyncGenerator[Dataset, None]:
    """Continuously receive and process messages from the WebSocket."""
    while True:
        message = await ws.receive_text()
        msg = Dataset()
        msg.parse(data=message, format="trig")
        yield msg


async def heartbeat(ws: WebSocket) -> None:
    """Send periodic heartbeat messages to the town."""
    try:
        while True:
            await trio.sleep(5)
            heartbeat = create_heartbeat_graph()
            await ws.send_text(heartbeat.serialize(format="trig"))
            logger.info("Sent heartbeat")
    except Exception as e:
        logger.error("Heartbeat error", error=e)


async def receive_datasets(
    ws: WebSocket,
) -> AsyncGenerator[Dataset, None]:
    async with trio.open_nursery() as nursery:
        nursery.start_soon(heartbeat, ws)
        async for msg in messages(ws):
            yield msg


def create_heartbeat_graph() -> Graph:
    """Create a heartbeat message graph."""
    heartbeat = Graph()
    hb_node = URIRef("#heartbeat")
    heartbeat.add((hb_node, RDF.type, NT.Heartbeat))
    heartbeat.add(
        (hb_node, PROV.generatedAtTime, Literal(datetime.now(UTC)))
    )
    return heartbeat
