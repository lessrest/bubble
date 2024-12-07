import sys
import traceback
from typing import AsyncGenerator, Tuple, Callable, Awaitable
from contextlib import asynccontextmanager
from urllib.parse import parse_qsl

import rich
import rich.traceback
import starlette
import starlette.responses
import trio
import httpx
import hypercorn
import hypercorn.trio
import structlog

from rdflib import Namespace, URIRef
from trio.abc import SendChannel, ReceiveChannel
from starlette.types import Send, Scope, Receive
from starlette.routing import Route
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.websockets import WebSocket
from starlette.applications import Starlette

from swash import mint
from bubble.logs import configure_logging
from bubble.cert import generate_self_signed_cert, create_ssl_context

from pydantic import BaseModel

# Configure structured logging at the start of the application.
configure_logging(colors=sys.stderr.isatty())
logger = structlog.get_logger()


class HttpRequestData(BaseModel):
    """
    A structured representation of an incoming HTTP request destined for an actor.
    """

    method: str
    headers: dict[str, str]
    path: str
    query_params: dict[str, str]
    body: bytes


class HttpResponseData(BaseModel):
    status: int
    headers: dict[str, str]
    body: bytes


class HttpRequestWithResponseCapability(BaseModel):
    model_config = {"arbitrary_types_allowed": True}
    request: HttpRequestData
    response: URIRef


class Town:
    """
    A Town represents a collection of actors, each identified by a URIRef.
    Actors can be dynamically spawned, and each is associated with a send channel.
    """

    def __init__(self, base_url: str):
        """
        Initialize the Town with the given base URL.

        :param base_url: The base HTTPS URL under which the Town and its actors operate.
        """
        self.actors: dict[URIRef, SendChannel] = {}
        self.base_url = base_url
        logger.info("initialized town", base=base_url)

    @asynccontextmanager
    async def spawn(
        self,
    ) -> AsyncGenerator[
        Tuple[
            URIRef,
            ReceiveChannel,
            Callable[[URIRef, dict], Awaitable[None]],
        ],
        None,
    ]:
        """
        Spawn a new actor with a unique URIRef and provide:
        - actor URI
        - a receive channel for it
        - a send function that allows sending messages to other actors by URIRef

        :yield: (actor_uri: URIRef, receive_channel: ReceiveChannel, send_message_func: Callable)
        """
        actor = mint.fresh_uri(Namespace(f"{self.base_url}/"))
        logger.info("spawning new actor", actor=actor)

        # Create a memory channel to communicate with this actor
        send_chan, recv_chan = trio.open_memory_channel(10)
        self.actors[actor] = send_chan

        async def send_message(target_actor: URIRef, message: dict):
            if target_actor in self.actors:
                await self.actors[target_actor].send(message)
            else:
                logger.warning(
                    "attempted to send message to non-existent actor",
                    target=target_actor,
                )

        async with send_chan:
            try:
                yield actor, recv_chan, send_message
            except Exception as e:
                logger.exception("error in spawn context", error=e)
                rich.print(e)
            finally:
                logger.info("despawning actor", actor=actor)
                del self.actors[actor]

    async def spawn_actor(
        self, nursery: trio.Nursery, actor_type: Callable, *args, **kwargs
    ) -> URIRef:
        actor = mint.fresh_uri(Namespace(f"{self.base_url}/"))
        logger.info("spawning new actor", actor=actor)

        # Create a memory channel to communicate with this actor
        send_chan, recv_chan = trio.open_memory_channel(10)
        self.actors[actor] = send_chan

        async def send_message(target_actor: URIRef, message: dict):
            if target_actor in self.actors:
                await self.actors[target_actor].send(message)
            else:
                logger.warning(
                    "attempted to send message to non-existent actor",
                    target=target_actor,
                )

        nursery.start_soon(
            actor_type, actor, recv_chan, send_message, *args, **kwargs
        )

        return actor


async def serve_app(app: Starlette, config: hypercorn.Config) -> None:
    """
    Serve the given Starlette application using Hypercorn in Trio's async environment.
    """
    await hypercorn.trio.serve(app, config, mode="asgi")  # type: ignore


async def verify_base_url(
    base_url: str, cert_path: str, key_path: str
) -> None:
    """
    Verify control over the given base_url by requesting its DID document endpoint over HTTPS.
    Uses a self-signed SSL certificate for local testing.
    """
    verification_url = f"{base_url}/.well-known/did.json"
    logger.info("verifying control over base URL", url=verification_url)

    ssl_context = create_ssl_context(cert_path, key_path)
    async with httpx.AsyncClient(verify=ssl_context) as client:
        response = await client.get(verification_url)
        response.raise_for_status()

    logger.info("successfully verified control over base URL")


def create_bootstrap_app() -> Starlette:
    """
    Create a bootstrap application that responds to DID document requests.
    Used temporarily to verify we have control over the base URL before starting the main app.
    """

    async def did_document(request):
        """
        Handle requests to the DID document endpoint.
        """
        host = (
            request.headers.get("host", "")
            .removeprefix("https://")
            .removesuffix("/")
        )
        did = f"did:web:{host}"
        document = {
            "@context": ["https://www.w3.org/ns/did/v1"],
            "id": did,
            "verificationMethod": [],
        }
        logger.info("responding to DID document request", document=document)
        return JSONResponse(document)

    @asynccontextmanager
    async def lifespan_context(app):
        logger.info("starting base URL verification server")
        try:
            yield
        finally:
            logger.info("stopping base URL verification server")

    return Starlette(
        routes=[Route("/.well-known/did.json", did_document)],
        lifespan=lifespan_context,
    )


async def root_actor(
    actor: URIRef,
    recv_chan: ReceiveChannel,
    send_func: Callable[[URIRef, dict], Awaitable[None]],
):
    """
    The root actor that handles messages from the websocket or HTTP requests.
    Now it can respond to incoming HTTP requests by sending a proper response back.
    """
    actor_logger = logger.bind(actor=actor)
    while True:
        actor_logger.info("waiting for message")
        message = await recv_chan.receive()
        # Attempt to parse the message as an HttpRequestWithResponseCapability
        try:
            request = HttpRequestWithResponseCapability.model_validate(
                message
            )
            actor_logger.info("request received by actor", request=request)
            # Construct a response
            response = HttpResponseData(
                status=200,
                headers={"Content-Type": "text/plain"},
                body=b"Hello from the root actor!",
            )
            # Send the response back to the specified response actor
            await send_func(request.response, response.model_dump())
        except Exception:
            actor_logger.warning(
                "invalid or unrecognized message received by actor",
                message=message,
            )


class FSRequest(BaseModel):
    """
    A general request format to the filesystem actors.
    You can customize this as needed.
    """

    action: str  # e.g. "list", "open"
    name: str | None = None  # For "open" requests
    # You could also include offset/length for partial reads, etc.


async def file_actor(
    actor: URIRef,
    recv_chan: ReceiveChannel,
    send_func: Callable[[URIRef, dict], Awaitable[None]],
    file_path: trio.Path,
):
    """
    A file actor that serves a single file in a read-only manner.
    Supports "open" action to return its entire content.
    """
    actor_logger = logger.bind(actor=actor, file=str(file_path))
    actor_logger.info("file actor spawned")
    while True:
        message = await recv_chan.receive()
        # We'll assume that messages arriving to a file actor have the same pattern as HTTP requests
        # or FSRequests. We'll try to interpret them first as HttpRequestWithResponseCapability
        # and then as FSRequest. In a more controlled environment, you'd define a clear message schema.
        try:
            request_with_response = (
                HttpRequestWithResponseCapability.model_validate(message)
            )
            request = request_with_response.request

            if request.method == "GET":
                if request.query_params.get("action") == "read":
                    # Read the file and return its content
                    if await file_path.is_file():
                        content = await file_path.read_bytes()
                        response_data = HttpResponseData(
                            status=200,
                            headers={
                                "Content-Type": "application/octet-stream"
                            },
                            body=content,
                        )
                        await send_func(
                            request_with_response.response,
                            response_data.model_dump(),
                        )
                        continue

                # Respond with a capability descriptor
                response_data = HttpResponseData(
                    status=200,
                    headers={"Content-Type": "application/json"},
                    body=JSONResponse(
                        {
                            "@context": ["https://node.town/2024/"],
                            "@type": "File",
                            "@id": actor,
                            "name": file_path.name,
                        }
                    ).body,
                )
                await send_func(
                    request_with_response.response,
                    response_data.model_dump(),
                )
                continue

            response_actor = request_with_response.response

            fs_req = FSRequest.model_validate_json(
                request.body.decode("utf-8") or "{}"
            )

            if fs_req.action == "open":
                if file_path.is_file():
                    content = await file_path.read_bytes()
                    response_data = HttpResponseData(
                        status=200,
                        headers={
                            "Content-Type": "application/octet-stream"
                        },
                        body=content,
                    )
                else:
                    response_data = HttpResponseData(
                        status=400,
                        headers={},
                        body=b"This actor does not represent a file",
                    )

                await send_func(response_actor, response_data.model_dump())
            else:
                response_data = HttpResponseData(
                    status=400,
                    headers={},
                    body=b"Unsupported action on a file actor",
                )
                await send_func(response_actor, response_data.model_dump())

        except Exception:
            actor_logger.warning(
                "invalid message received", message=message
            )


rich.traceback.install()


async def filesystem_actor(
    actor: URIRef,
    recv_chan: ReceiveChannel,
    send_func: Callable[[URIRef, dict], Awaitable[None]],
    spawn_func: Callable[[trio.Nursery, trio.Path], Awaitable[URIRef]],
    directory: trio.Path,
):
    """
    A filesystem actor that represents a directory.
    On spawn, it lists all entries in the directory and spawns an actor for each:
      - For a subdirectory, another filesystem_actor is spawned.
      - For a file, a file_actor is spawned.

    On HTTP request, if action == "list", returns JSON listing of names -> actor URIs.
    If action == "open" and name is given, forwards request to the corresponding actor.
    """
    actor_logger = logger.bind(actor=actor, directory=str(directory))
    actor_logger.info("filesystem_actor spawned")

    entries: dict[str, URIRef] = {}

    async with trio.open_nursery() as nursery:
        # Pre-spawn actors for each entry in the directory
        async def spawn_entry(entry: trio.Path) -> URIRef:
            # We'll spawn either a file_actor or another filesystem_actor
            child_actor = await spawn_func(nursery, entry)
            return child_actor

        for entry in await directory.iterdir():
            # Spawn an actor for each entry
            child_actor = await spawn_entry(entry)
            entries[entry.name] = child_actor

        # Now run the main loop to handle requests
        while True:
            message = await recv_chan.receive()
            try:
                request_with_response = (
                    HttpRequestWithResponseCapability.model_validate(
                        message
                    )
                )
                request = request_with_response.request
                response_actor = request_with_response.response

                # Try to parse the request body as a FSRequest
                try:
                    fs_req = FSRequest.model_validate_json(
                        request.body.decode("utf-8") or "{}"
                    )
                except Exception:
                    # If no valid FSRequest is provided, assume "list"
                    fs_req = FSRequest(action="list")

                actor_logger.info(
                    "filesystem_actor received request",
                    fs_req=fs_req.model_dump(),
                )

                if fs_req.action == "list":
                    # Return a JSON with entries
                    listing = {
                        name: str(uri) for name, uri in entries.items()
                    }
                    response_data = HttpResponseData(
                        status=200,
                        headers={"Content-Type": "application/json"},
                        body=JSONResponse(listing).body,
                    )
                    await send_func(
                        response_actor, response_data.model_dump()
                    )

                elif fs_req.action == "open" and fs_req.name is not None:
                    # Forward the request to the appropriate child actor if exists
                    if fs_req.name in entries:
                        target_actor = entries[fs_req.name]
                        # Forward the original request to target actor
                        await send_func(
                            target_actor, request_with_response.model_dump()
                        )
                    else:
                        response_data = HttpResponseData(
                            status=404,
                            headers={},
                            body=b"No such file or directory",
                        )
                        await send_func(
                            response_actor, response_data.model_dump()
                        )

                else:
                    response_data = HttpResponseData(
                        status=400,
                        headers={},
                        body=b"Unsupported action or missing parameters",
                    )
                    await send_func(
                        response_actor, response_data.model_dump()
                    )

            except Exception as e:
                actor_logger.warning(
                    "invalid message received by filesystem actor",
                    message=message,
                    error=str(e),
                )


async def get_request_body(receive: Receive) -> bytes:
    """
    Read the entire request body from the ASGI receive channel.
    """
    body = b""
    more_body = True
    while more_body:
        message = await receive()
        if message["type"] == "http.request":
            body += message.get("body", b"")
            more_body = message.get("more_body", False)
        elif message["type"] == "http.disconnect":
            break
    return body


async def main_app(
    scope: Scope,
    receive: Receive,
    send: Send,
    town: Town,
    bootstrap_app: Starlette,
):
    """
    The main application callable (ASGI) handling lifespan, DID document requests,
    actor websockets, and HTTP requests destined for actors.
    """

    async def spawn_func(nursery: trio.Nursery, path: trio.Path) -> URIRef:
        return await town.spawn_actor(nursery, file_actor, path)

    if scope["type"] == "lifespan":
        try:
            # Handle startup/shutdown signals
            async with trio.open_nursery() as nursery:
                async with town.spawn() as (actor, recv_chan, send_func):
                    nursery.start_soon(
                        root_actor, actor, recv_chan, send_func
                    )
                    async with town.spawn() as (
                        directory_actor,
                        directory_recv_chan,
                        directory_send_func,
                    ):
                        directory = trio.Path(".")
                        nursery.start_soon(
                            filesystem_actor,
                            directory_actor,
                            directory_recv_chan,
                            directory_send_func,
                            spawn_func,
                            directory,
                        )
                        try:
                            while True:
                                message = await receive()
                                if message["type"] == "lifespan.shutdown":
                                    await send(
                                        {
                                            "type": "lifespan.shutdown.complete"
                                        }
                                    )
                                    return
                                elif message["type"] == "lifespan.startup":
                                    await send(
                                        {
                                            "type": "lifespan.startup.complete"
                                        }
                                    )
                        finally:
                            logger.info("lifespan completed")
        except* Exception as e:
            logger.error("lifespan failed", error=str(e))
            rich.print(e)
            for tb in e.exceptions:
                rich.inspect(tb)
                if isinstance(tb, ExceptionGroup):
                    for sub_tb in tb.exceptions:
                        traceback.print_exception(sub_tb)
            raise e

    elif scope["type"] == "http":
        # Handle HTTP requests
        path = scope["path"]
        if path == "/.well-known/did.json":
            # Serve the DID document from the bootstrap app
            return await bootstrap_app(scope, receive, send)
        else:
            # Check if this path corresponds to an actor
            actor = URIRef(f"{town.base_url}{path}")
            if actor in town.actors:
                # Build the ActorRequest
                method = scope["method"]
                raw_headers = scope.get("headers", [])
                headers = {
                    k.decode("latin-1"): v.decode("latin-1")
                    for k, v in raw_headers
                }
                query_string = scope.get("query_string", b"")
                query_params = dict(
                    parse_qsl(query_string.decode("latin-1"))
                )

                # Read the request body
                body = await get_request_body(receive)

                async with town.spawn() as (
                    response_actor,
                    response_recv_chan,
                    response_send_func,
                ):
                    actor_logger = logger.bind(actor=response_actor)
                    request_data = HttpRequestData(
                        method=method,
                        headers=headers,
                        path=path,
                        query_params=query_params,
                        body=body,
                    )
                    request_model = HttpRequestWithResponseCapability(
                        request=request_data,
                        response=response_actor,
                    )

                    # Send the request structure to the target actor's mailbox
                    await town.actors[actor].send(
                        request_model.model_dump()
                    )

                    # Wait for the response
                    response_model = await response_recv_chan.receive()
                    try:
                        response_data = HttpResponseData.model_validate(
                            response_model
                        )
                        actor_logger.info(
                            "response received by actor",
                            response=response_data,
                        )
                    except Exception:
                        actor_logger.warning(
                            "invalid response received by actor",
                            response=response_model,
                        )
                        response_data = HttpResponseData(
                            status=500,
                            headers={},
                            body=b"Invalid response from actor",
                        )

                    response = starlette.responses.Response(
                        content=response_data.body,
                        status_code=response_data.status,
                        headers=response_data.headers,
                    )

                    await response(scope, receive, send)
                    return
            else:
                # No such actor, return 404
                logger.warning("no matching actor for request", path=path)
                response = PlainTextResponse("Not found", status_code=404)
                await response(scope, receive, send)

    elif scope["type"] == "websocket":
        # Handle WebSocket connections for actors
        websocket = WebSocket(scope, receive=receive, send=send)
        path = scope["path"]
        actor = URIRef(f"{town.base_url}{path}")

        if actor not in town.actors:
            logger.warning(
                "received connection for invalid actor", actor=actor
            )
            await websocket.close(code=4004, reason="Invalid actor")
            return

        logger.info("actor connected via websocket", actor=actor)
        await websocket.accept()

        try:
            while True:
                data = await websocket.receive_text()
                logger.debug(
                    "received websocket message from actor",
                    actor=actor,
                    length=len(data),
                )
                await town.actors[actor].send(data)
        except Exception as e:
            logger.info("actor disconnected", actor=actor, error=str(e))
            await websocket.close()

    else:
        # Any other request type is not supported
        logger.warning("invalid request type", type=scope["type"])
        response = PlainTextResponse("Not found", status_code=404)
        await response(scope, receive, send)


async def new_town(base_url: str, bind: str):
    """
    Create a new town application that:
    - Verifies HTTPS control via a temporary bootstrap app and DID document.
    - Uses self-signed certificates if none are provided.
    - Returns the main ASGI application once verification is complete.
    """
    if not base_url.startswith("https://"):
        logger.error(
            "base URL must start with https:// to enable TLS", base=base_url
        )
        raise ValueError("base_url must use HTTPS")

    # Create a temporary bootstrap app for DID document verification
    bootstrap_app = create_bootstrap_app()

    # Generate a self-signed certificate for testing and set up the Hypercorn config
    hostname = base_url.replace("https://", "").rstrip("/")
    cert_path, key_path = generate_self_signed_cert(hostname)

    config = hypercorn.Config()
    config.bind = [bind]
    config.certfile = cert_path
    config.keyfile = key_path
    config.log.error_logger = logger.bind(name="hypercorn.error")

    # Run the bootstrap server to verify the DID document
    async with trio.open_nursery() as nursery:
        nursery.start_soon(serve_app, bootstrap_app, config)

        try:
            await verify_base_url(base_url, cert_path, key_path)
        except Exception as e:
            logger.error(
                "failed to verify control over base URL", error=str(e)
            )
            raise RuntimeError(f"Failed to verify base URL {base_url}: {e}")
        finally:
            # Stop the bootstrap server after verification
            nursery.cancel_scope.cancel()

    # Create the main Town and return its ASGI application
    town = Town(base_url)

    async def app(scope: Scope, receive: Receive, send: Send):
        return await main_app(scope, receive, send, town, bootstrap_app)

    return app
