from dataclasses import dataclass
import sys
from contextlib import asynccontextmanager
from urllib.parse import parse_qsl

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

    def to_response(self) -> starlette.responses.Response:
        return starlette.responses.Response(
            content=self.body,
            status_code=self.status,
            headers=self.headers,
        )

    async def send(self, scope: Scope, receive: Receive, send: Send):
        response = self.to_response()
        await response(scope, receive, send)


class HttpRequestWithResponseCapability(BaseModel):
    model_config = {"arbitrary_types_allowed": True}
    request: HttpRequestData
    response: URIRef


class ActorContext:
    """
    Encapsulates the context needed for an actor to operate, including its URI,
    receive channel, and nursery for spawning child actors.
    """

    def __init__(
        self,
        actor: URIRef,
        receiver: ReceiveChannel,
        town: "Town",
        nursery: trio.Nursery,
    ):
        self.actor = actor
        self.receiver = receiver
        self.town = town
        self.nursery = nursery
        self.logger = structlog.get_logger().bind(actor=actor)

    async def send(self, target: URIRef, message: dict):
        """Helper method to send a message to another actor"""
        await self.town.send(target, message)


class Actor[Param]:
    """
    Base class for all actors in the system.
    Provides common functionality and a standard interface.
    """

    def __init__(self, context: ActorContext, param: Param):
        """
        Initialize the actor with its context.

        :param context: The ActorContext providing access to actor capabilities
        :param param: The parameter to pass to the actor's run method
        """
        self.context = context
        self.param = param
        self.logger = self.context.logger

    async def run(self):
        """
        Main entry point for actor execution. All actors must implement this method.
        """
        raise NotImplementedError("Actors must implement run()")

    async def spawn_child[Param2](
        self, actor_type: type["Actor[Param2]"], param: Param2
    ) -> URIRef:
        """Spawn a child actor in this actor's nursery"""
        actor_id, receiver, _ = self.context.town._create_actor()
        self.context.nursery.start_soon(actor_type(self.context, param).run)
        return actor_id

    async def handle_message(self, message: dict) -> None:
        """
        Default message handler that processes HTTP requests.
        Actors can override this to handle different message types.
        """
        try:
            request = HttpRequestWithResponseCapability.model_validate(
                message
            )
            self.logger.info("request received by actor", request=request)
            await self.handle_http_request(request)
        except Exception as e:
            self.logger.warning(
                "invalid or unrecognized message received by actor",
                message=message,
                error=str(e),
            )

    async def handle_http_request(
        self,
        request: HttpRequestWithResponseCapability,
    ) -> None:
        """
        Handle HTTP requests. Actors should override this method to provide custom HTTP handling.
        """
        response = HttpResponseData(
            status=501,
            headers={"Content-Type": "text/plain"},
            body=b"Not implemented",
        )
        await self.context.send(request.response, response.model_dump())

    async def receive(self):
        """Helper method to receive the next message"""
        return await self.context.receiver.receive()

    async def receive_model[T: BaseModel](self, model_class: type[T]) -> T:
        """
        Receive and validate a message against a Pydantic model.

        :param model_class: The Pydantic model class to validate against
        :return: An instance of the model class
        :raises: ValidationError if the message doesn't match the model
        """
        message = await self.receive()
        try:
            return model_class.model_validate(message)
        except Exception as e:
            self.logger.warning(
                "failed to validate received message",
                model=model_class.__name__,
                error=str(e),
                message=message,
            )
            raise

    async def send(self, target: URIRef, model: BaseModel):
        """Send a message to another actor"""
        await self.context.town.send(target, model.model_dump())


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

    async def send(self, target_actor: URIRef, message: dict):
        """Helper method to send messages between actors"""
        if target_actor in self.actors:
            await self.actors[target_actor].send(message)
        else:
            logger.warning(
                "attempted to send message to non-existent actor",
                target=target_actor,
            )

    async def run_actor[Param](
        self,
        actor_type: type["Actor[Param]"],
        param: Param,
    ):
        async with self.using_actor(actor_type, param):
            pass

    @asynccontextmanager
    async def using_actor[Param](
        self, actor_type: type["Actor[Param]"], param: Param
    ):
        async with trio.open_nursery() as nursery:
            actor, receiver, _ = self._create_actor()
            context = ActorContext(
                actor,
                receiver,
                self,
                nursery,
            )
            instance = actor_type(context, param)
            try:
                nursery.start_soon(instance.run)
                yield actor
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


class FSRequest(BaseModel):
    """
    A general request format to the filesystem actors.
    You can customize this as needed.
    """

    action: str  # e.g. "list", "open"
    name: str | None = None  # For "open" requests
    # You could also include offset/length for partial reads, etc.


class FileActor(Actor[trio.Path]):
    """
    A file actor that serves a single file in a read-only manner.
    """

    async def run(self):
        self.logger.info("file actor spawned", file=str(self.param))

        while True:
            message = await self.receive()
            await self.handle_message(message)

    async def handle_http_request(
        self,
        request: HttpRequestWithResponseCapability,
    ):
        req = request.request

        if req.method == "GET":
            if req.query_params.get("action") == "read":
                if await self.param.is_file():
                    content = await self.param.read_bytes()
                    response = HttpResponseData(
                        status=200,
                        headers={
                            "Content-Type": "application/octet-stream"
                        },
                        body=content,
                    )
                    await self.context.send(
                        request.response, response.model_dump()
                    )
                    return

            # Respond with a capability descriptor
            response = HttpResponseData(
                status=200,
                headers={"Content-Type": "application/json"},
                body=JSONResponse(
                    {
                        "@context": ["https://node.town/2024/"],
                        "@type": "File",
                        "@id": self.context.actor,
                        "name": self.param.name,
                    }
                ).body,
            )
            await self.context.send(request.response, response.model_dump())
            return

        try:
            fs_req = FSRequest.model_validate_json(
                req.body.decode("utf-8") or "{}"
            )

            if fs_req.action == "open":
                if await self.param.is_file():
                    content = await self.param.read_bytes()
                    response = HttpResponseData(
                        status=200,
                        headers={
                            "Content-Type": "application/octet-stream"
                        },
                        body=content,
                    )
                else:
                    response = HttpResponseData(
                        status=400,
                        headers={},
                        body=b"This actor does not represent a file",
                    )
            else:
                response = HttpResponseData(
                    status=400,
                    headers={},
                    body=b"Unsupported action on a file actor",
                )

            await self.context.send(request.response, response.model_dump())

        except Exception as e:
            self.logger.warning("error handling request", error=str(e))
            response = HttpResponseData(
                status=400,
                headers={},
                body=b"Invalid request",
            )
            await self.context.send(request.response, response.model_dump())


class FilesystemActor(Actor[trio.Path]):
    """
    A filesystem actor that represents a directory.
    """

    async def run(self):
        self.logger.info(
            "filesystem_actor spawned", directory=str(self.param)
        )
        self.entries: dict[str, URIRef] = {}

        for entry in await self.param.iterdir():
            child_actor = await self.spawn_child(FileActor, entry)
            self.entries[entry.name] = child_actor

        while True:
            message = await self.receive()
            await self.handle_message(message)

    async def handle_http_request(
        self,
        request: HttpRequestWithResponseCapability,
    ):
        try:
            fs_req = FSRequest.model_validate_json(
                request.request.body.decode("utf-8") or "{}"
            )
        except Exception:
            fs_req = FSRequest(action="list")

        if fs_req.action == "list":
            listing = {name: str(uri) for name, uri in self.entries.items()}
            response = HttpResponseData(
                status=200,
                headers={"Content-Type": "application/json"},
                body=JSONResponse(listing).body,
            )
            await self.context.send(request.response, response.model_dump())

        elif fs_req.action == "open" and fs_req.name is not None:
            if fs_req.name in self.entries:
                target_actor = self.entries[fs_req.name]
                await self.context.send(target_actor, request.model_dump())
            else:
                response = HttpResponseData(
                    status=404,
                    headers={},
                    body=b"No such file or directory",
                )
                await self.context.send(
                    request.response, response.model_dump()
                )

        else:
            response = HttpResponseData(
                status=400,
                headers={},
                body=b"Unsupported action or missing parameters",
            )
            await self.context.send(request.response, response.model_dump())


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


@dataclass
class HTTPRequestContext:
    scope: Scope
    receive: Receive
    send: Send
    target: URIRef


async def read_http_request(
    scope: Scope, receive: Receive, path: str
) -> HttpRequestData:
    method = scope["method"]
    raw_headers = scope.get("headers", [])
    headers = {
        k.decode("latin-1"): v.decode("latin-1") for k, v in raw_headers
    }
    query_string = scope.get("query_string", b"")
    query_params = dict(parse_qsl(query_string.decode("latin-1")))

    body = await get_request_body(receive)

    request_data = HttpRequestData(
        method=method,
        headers=headers,
        path=path,
        query_params=query_params,
        body=body,
    )

    return request_data


class RequestHandlingActor(Actor[HTTPRequestContext]):
    async def run(self):
        request = await read_http_request(
            self.param.scope, self.param.receive, self.param.target
        )

        request_model = HttpRequestWithResponseCapability(
            request=request,
            response=self.context.actor,
        )

        await self.send(self.param.target, request_model)
        try:
            response = await self.receive_model(HttpResponseData)
        except Exception:
            response = HttpResponseData(
                status=500,
                headers={},
                body=b"Invalid response from actor",
            )

        await response.send(
            self.param.scope, self.param.receive, self.param.send
        )


class MessageForActor(BaseModel):
    """
    A message format for sending messages to actors.
    """

    target: str
    message: dict


class RootActor(Actor[None]):
    """
    The root actor that handles messages from the websocket or HTTP requests.
    """

    async def run(self):
        await self.spawn_child(FilesystemActor, trio.Path("vocab"))
        while True:
            message = await self.receive()
            await self.handle_message(message)

    async def handle_http_request(
        self,
        request: HttpRequestWithResponseCapability,
    ):
        response = HttpResponseData(
            status=200,
            headers={"Content-Type": "text/plain"},
            body=b"Hello from the root actor!",
        )
        await self.context.send(request.response, response.model_dump())


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
            async with town.using_actor(RootActor, None):
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
            return await bootstrap_app(scope, receive, send)
        else:
            target = URIRef(f"{town.base_url}{path}")
            if target in town.actors:
                await town.run_actor(
                    RequestHandlingActor,
                    HTTPRequestContext(scope, receive, send, target),
                )
            else:
                # No such actor, return 404
                logger.warning("no matching actor for request", path=path)
                response = PlainTextResponse("Not found", status_code=404)
                await response(scope, receive, send)

    elif scope["type"] == "websocket":
        websocket = WebSocket(scope, receive=receive, send=send)
        await websocket.accept()
        logger.info("accepted WebSocket client", scope=scope)

        try:
            while True:
                json_data = await websocket.receive_text()
                message = MessageForActor.model_validate_json(json_data)

                target = URIRef(message.target)
                if target in town.actors:
                    await town.send(target, message.message)
                else:
                    logger.warning(
                        "no matching actor for request", target=target
                    )
                    await websocket.close(code=4004, reason="Invalid actor")
                    return

        except Exception as e:
            logger.info("peer disconnected", error=str(e))
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
    #    config.log.access_logger = logger.bind(name="hypercorn.access")

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
