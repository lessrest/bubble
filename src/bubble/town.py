import sys
from typing import Callable, Awaitable
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


class ActorContext:
    """
    Encapsulates the context needed for an actor to operate, including its URI,
    receive channel, send function, and nursery for spawning child actors.
    """

    def __init__(
        self,
        actor: URIRef,
        receiver: ReceiveChannel,
        send_message: Callable[[URIRef, dict], Awaitable[None]],
        nursery: trio.Nursery,
        spawn: Callable[[trio.Nursery, Callable, ...], Awaitable[URIRef]],
    ):
        self.actor = actor
        self.receiver = receiver
        self.send_message = send_message
        self.nursery = nursery
        self.spawn = spawn
        self.logger = structlog.get_logger().bind(actor=actor)

    async def send(self, target: URIRef, message: dict):
        """Helper method to send a message to another actor"""
        await self.send_message(target, message)

    async def receive(self):
        """Helper method to receive the next message"""
        return await self.receiver.receive()

    async def spawn_child(
        self, actor_type: Callable, *args, **kwargs
    ) -> URIRef:
        """Spawn a child actor in this actor's nursery"""
        return await self.spawn(self.nursery, actor_type, *args, **kwargs)


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

    def _create_actor(
        self,
    ) -> tuple[URIRef, trio.MemoryReceiveChannel, trio.MemorySendChannel]:
        """Helper method to create a new actor with channels"""
        actor = mint.fresh_uri(Namespace(f"{self.base_url}/"))
        logger.info("spawning new actor", actor=actor)
        sender, receiver = trio.open_memory_channel(10)
        self.actors[actor] = sender
        return actor, receiver, sender

    async def _send_message(self, target_actor: URIRef, message: dict):
        """Helper method to send messages between actors"""
        if target_actor in self.actors:
            await self.actors[target_actor].send(message)
        else:
            logger.warning(
                "attempted to send message to non-existent actor",
                target=target_actor,
            )

    async def spawn_actor(
        self, nursery: trio.Nursery, actor_type: Callable, *args, **kwargs
    ) -> URIRef:
        actor, receiver, _ = self._create_actor()

        context = ActorContext(
            actor,
            receiver,
            self._send_message,
            nursery,
            self.spawn_actor,
        )

        nursery.start_soon(actor_type, context, *args, **kwargs)

        return actor

    async def run_actor(self, actor_type: Callable, *args, **kwargs):
        async with trio.open_nursery() as nursery:
            actor, receiver, _ = self._create_actor()
            context = ActorContext(
                actor,
                receiver,
                self._send_message,
                nursery,
                self.spawn_actor,
            )
            try:
                await actor_type(context, *args, **kwargs)
            finally:
                logger.info("actor completed", actor=actor)
                del self.actors[actor]


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


async def root_actor(this: ActorContext):
    """
    The root actor that handles messages from the websocket or HTTP requests.
    """
    while True:
        this.logger.info("waiting for message")
        message = await this.receive()
        try:
            request = HttpRequestWithResponseCapability.model_validate(
                message
            )
            this.logger.info("request received by actor", request=request)
            response = HttpResponseData(
                status=200,
                headers={"Content-Type": "text/plain"},
                body=b"Hello from the root actor!",
            )
            await this.send(request.response, response.model_dump())
        except Exception:
            this.logger.warning(
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
    this: ActorContext,
    file_path: trio.Path,
):
    """
    A file actor that serves a single file in a read-only manner.
    Supports "open" action to return its entire content.
    """
    this.logger.info("file actor spawned", file=str(file_path))

    while True:
        message = await this.receive()
        try:
            request_with_response = (
                HttpRequestWithResponseCapability.model_validate(message)
            )
            request = request_with_response.request

            if request.method == "GET":
                if request.query_params.get("action") == "read":
                    if await file_path.is_file():
                        content = await file_path.read_bytes()
                        response_data = HttpResponseData(
                            status=200,
                            headers={
                                "Content-Type": "application/octet-stream"
                            },
                            body=content,
                        )
                        await this.send(
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
                            "@id": this.actor,
                            "name": file_path.name,
                        }
                    ).body,
                )
                await this.send(
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

                await this.send(response_actor, response_data.model_dump())
            else:
                response_data = HttpResponseData(
                    status=400,
                    headers={},
                    body=b"Unsupported action on a file actor",
                )
                await this.send(response_actor, response_data.model_dump())

        except Exception:
            this.logger.warning("invalid message received", message=message)


rich.traceback.install()


async def filesystem_actor(
    this: ActorContext,
    directory: trio.Path,
):
    """
    A filesystem actor that represents a directory.
    """
    this.logger.info("filesystem_actor spawned", directory=str(directory))

    entries: dict[str, URIRef] = {}

    for entry in await directory.iterdir():
        child_actor = await this.spawn_child(file_actor, entry)
        entries[entry.name] = child_actor

    # Now run the main loop to handle requests
    while True:
        message = await this.receive()
        try:
            request_with_response = (
                HttpRequestWithResponseCapability.model_validate(message)
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

            this.logger.info(
                "filesystem_actor received request",
                fs_req=fs_req.model_dump(),
            )

            if fs_req.action == "list":
                # Return a JSON with entries
                listing = {name: str(uri) for name, uri in entries.items()}
                response_data = HttpResponseData(
                    status=200,
                    headers={"Content-Type": "application/json"},
                    body=JSONResponse(listing).body,
                )
                await this.send(response_actor, response_data.model_dump())

            elif fs_req.action == "open" and fs_req.name is not None:
                # Forward the request to the appropriate child actor if exists
                if fs_req.name in entries:
                    target_actor = entries[fs_req.name]
                    # Forward the original request to target actor
                    await this.send(
                        target_actor, request_with_response.model_dump()
                    )
                else:
                    response_data = HttpResponseData(
                        status=404,
                        headers={},
                        body=b"No such file or directory",
                    )
                    await this.send(
                        response_actor, response_data.model_dump()
                    )

            else:
                response_data = HttpResponseData(
                    status=400,
                    headers={},
                    body=b"Unsupported action or missing parameters",
                )
                await this.send(response_actor, response_data.model_dump())

        except Exception as e:
            this.logger.warning(
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

    if scope["type"] == "lifespan":
        try:
            async with trio.open_nursery() as nursery:
                await town.spawn_actor(nursery, root_actor)
                await town.spawn_actor(
                    nursery, filesystem_actor, trio.Path(".")
                )

                while True:
                    message = await receive()
                    if message["type"] == "lifespan.shutdown":
                        await send({"type": "lifespan.shutdown.complete"})
                        return
                    elif message["type"] == "lifespan.startup":
                        await send({"type": "lifespan.startup.complete"})
        finally:
            logger.info("lifespan completed")

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

                async def response_actor(this: ActorContext):
                    request_data = HttpRequestData(
                        method=method,
                        headers=headers,
                        path=path,
                        query_params=query_params,
                        body=body,
                    )
                    request_model = HttpRequestWithResponseCapability(
                        request=request_data,
                        response=this.actor,
                    )

                    # Send the request structure to the target actor's mailbox
                    await town.actors[actor].send(
                        request_model.model_dump()
                    )

                    # Wait for the response
                    response_model = await this.receive()
                    try:
                        response_data = HttpResponseData.model_validate(
                            response_model
                        )
                        this.logger.info(
                            "response received by actor",
                            response=response_data,
                        )
                    except Exception:
                        this.logger.warning(
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

                await town.run_actor(response_actor)

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
