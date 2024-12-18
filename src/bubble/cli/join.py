import trio
import structlog
from typer import Option
from rdflib import URIRef
from fastapi import WebSocket
from cryptography.hazmat.primitives.asymmetric import ed25519

from bubble.cli.app import app
from bubble.sock.join import (
    receive_datasets,
    signed_connection,
    anonymous_connection,
)


@app.command()
def join(
    town: str = Option(..., "--town", help="Town URL to join"),
    anonymous: bool = Option(
        False, "--anonymous", help="Join anonymously without an identity"
    ),
) -> None:
    """Join a remote town as a simple peer that prints incoming messages."""
    trio.run(_bubble_join, town, anonymous)


async def _bubble_join(town: str, anonymous: bool) -> None:
    logger = structlog.get_logger()

    async def handle_dataset_receiving(ws: WebSocket, actor_uri: URIRef):
        logger.info("connected to town", actor_uri=actor_uri)
        async for msg in receive_datasets(ws):
            logger.debug("Received dataset", graph=msg)

    def generate_key_pair():
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        return private_key, public_key

    try:
        if anonymous:
            async with anonymous_connection(town) as (ws, me):
                await handle_dataset_receiving(ws, me)

        else:
            sec, pub = generate_key_pair()
            async with signed_connection(town, sec, pub) as (ws, me):
                await handle_dataset_receiving(ws, me)

    except Exception as e:
        logger.error("connection failed", error=e)
        raise
