import sys
from typing import AsyncGenerator
from contextlib import asynccontextmanager

import trio
import httpx
import hypercorn
import hypercorn.trio

from rdflib import URIRef
from trio.abc import SendChannel, ReceiveChannel
from starlette.types import Send, Scope, Receive
from starlette.routing import Route
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.websockets import WebSocket
from starlette.applications import Starlette

from swash import mint

import structlog
from bubble.logs import configure_logging

# At the start of your application:
configure_logging(colors=sys.stderr.isatty())

logger = structlog.get_logger()


class Town:
    actors: dict[URIRef, SendChannel]

    def __init__(self, base_url: str):
        self.actors = {}
        self.base_url = base_url
        logger.info("initialized town", base_url=base_url)

    @asynccontextmanager
    async def spawn(
        self,
    ) -> AsyncGenerator[tuple[URIRef, ReceiveChannel], None]:
        actor = mint.fresh_iri()
        logger.info("spawning new actor", actor=actor)
        async with trio.open_nursery():
            send, recv = trio.open_memory_channel(10)
            self.actors[actor] = send
            async with send:
                try:
                    yield actor, recv
                finally:
                    logger.info("despawning actor", actor=actor)
                    del self.actors[actor]


async def serve(app: Starlette, config: hypercorn.Config) -> None:
    await hypercorn.trio.serve(app, config, mode="asgi")  # type: ignore


async def new_town(base_url: str, bind: str):
    # First create a bootstrap app to verify the base URL
    async def did_document(request):
        did = f"did:web:{base_url.removeprefix('https://')}"
        logger.info("responding to DID document request", did=did)
        return JSONResponse(
            {
                "@context": ["https://www.w3.org/ns/did/v1"],
                "id": did,
                "verificationMethod": [],
                "service": [
                    {
                        "id": "#ws",
                        "type": "WebSocketEndpoint",
                        "serviceEndpoint": base_url.replace(
                            "https://", "wss://"
                        ),
                    }
                ],
            }
        )

    bootstrap_app = Starlette(
        routes=[Route("/.well-known/did.json", did_document)]
    )

    logger.info("starting base URL verification server", bind=bind)
    async with trio.open_nursery() as nursery:
        config = hypercorn.Config()
        config.bind = [bind]
        config.log.error_logger = logger.bind()

        nursery.start_soon(serve, bootstrap_app, config)

        # Verify we can reach our own DID document
        try:
            http_url = base_url.replace("wss://", "https://")
            logger.info(
                "verifying control over base URL",
                url=f"{http_url}/.well-known/did.json",
            )
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{http_url}/.well-known/did.json"
                )
                response.raise_for_status()
            logger.info("successfully verified control over base URL")

        except Exception as e:
            logger.error(
                "failed to verify control over base URL", error=str(e)
            )
            raise RuntimeError(f"Failed to verify base URL {base_url}: {e}")
        finally:
            nursery.cancel_scope.cancel()

    # Now create the main town and websocket app
    town = Town(base_url)

    async def app(scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
                elif message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})

        # Handle DID document requests
        if (
            scope["type"] == "http"
            and scope["path"] == "/.well-known/did.json"
        ):
            return await bootstrap_app(scope, receive, send)

        # Handle websocket connections
        if scope["type"] != "websocket":
            logger.warning("invalid request type", type=scope["type"])
            return await PlainTextResponse("Not found", status_code=404)(
                scope, receive, send
            )

        websocket = WebSocket(scope, receive=receive, send=send)
        path = scope["path"]
        actor = URIRef(f"{town.base_url}{path}")

        if actor not in town.actors:
            logger.warning(
                "received connection for invalid actor", actor=actor
            )
            await websocket.close(code=4004, reason="Invalid actor")
            return

        logger.info("actor connected", actor=actor)
        await websocket.accept()

        try:
            while True:
                data = await websocket.receive_text()
                logger.debug(
                    "received message from actor",
                    actor=actor,
                    length=len(data),
                )
                await town.actors[actor].send(data)
        except Exception as e:
            logger.info("actor disconnected", actor=actor, error=str(e))
            await websocket.close()

    return app
