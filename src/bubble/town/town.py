from dataclasses import dataclass
import sys
from urllib.parse import parse_qsl
from typing import Protocol

import starlette
import starlette.responses
import trio
import httpx
import hypercorn
import hypercorn.trio
import structlog

from rdflib import Namespace, URIRef
from trio.abc import SendChannel
from starlette.types import Send, Scope, Receive, Message
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.websockets import WebSocket
from starlette.applications import Starlette

from swash import mint
from bubble.logs import configure_logging

# from bubble.town.fsys import FilesystemActor
from bubble.town.cert import generate_self_signed_cert, create_ssl_context

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


class ActorHttpRequest(BaseModel):
    model_config = {"arbitrary_types_allowed": True}
    request: HttpRequestData
    response: URIRef


class TownProtocol(Protocol):
    """
    Protocol defining the interface that ActorContext needs from Town.
    This decouples the ActorContext from the specific Town implementation.
    """

    async def send(self, target: URIRef, message: dict) -> None:
        """Send a message to a target actor"""
        ...

    def register_actor(self) -> tuple[URIRef, trio.MemoryReceiveChannel]:
        """Register a new actor in the town"""
        ...

    def unregister_actor(self, actor: URIRef) -> None:
        """Unregister an actor from the town"""
        ...


class ActorContext:
    """
    Encapsulates the context needed for an actor to operate, including its URI,
    receive channel, and nursery for spawning child actors.
    """

    def __init__(
        self,
        actor: URIRef,
        receiver: Receive,
        town: "Town",
        nursery: trio.Nursery,
    ):
        self.actor = actor
        self.receiver = receiver
        self.town = town
        self.nursery = nursery
        self.logger = structlog.get_logger().bind(actor=actor)

    async def send(self, target: URIRef, message: Message):
        """Helper method to send a message to another actor"""
        await self.town.send(target, message)

    async def receive(self) -> Message:
        return await self.receiver()

    async def receive_model[T: BaseModel](self, model_class: type[T]) -> T:
        message = await self.receive()
        return model_class.model_validate(message)

    async def send_model(self, target: URIRef, model: BaseModel):
        await self.send(target, model.model_dump())

    async def spawn[Param2](
        self, actor_type: type["Actor[Param2]"], param: Param2
    ) -> URIRef:
        actor_id, receiver = self.town.register_actor()
        self = ActorContext(
            actor_id, receiver.receive, self.town, self.nursery
        )

        self.nursery.start_soon(actor_type(self.town, param).run, self)

        return actor_id


class Actor[Param]:
    """
    Base class for all actors in the system.
    Provides common functionality and a standard interface.
    """

    town: "Town"

    def __init__(self, town: "Town", param: Param):
        self.town = town
        self.param = param
        self.logger = structlog.get_logger().bind(actor=self.param)

    async def __call__(self):
        async with trio.open_nursery() as nursery:
            actor, channel = self.town.register_actor()
            context = ActorContext(
                actor, channel.receive, self.town, nursery
            )
            try:
                await self.run(context)
            finally:
                self.town.unregister_actor(actor)

    async def run(self, context: ActorContext):
        raise NotImplementedError("Actors must implement run()")


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

    def register_actor(
        self,
    ) -> tuple[URIRef, trio.MemoryReceiveChannel]:
        """Helper method to create a new actor with channels"""
        actor = mint.fresh_uri(Namespace(f"{self.base_url}/"))
        logger.info("registering actor", actor=actor)
        sender, receiver = trio.open_memory_channel(10)
        self.actors[actor] = sender
        return actor, receiver

    def unregister_actor(self, actor: URIRef) -> None:
        """Helper method to remove an actor from the town"""
        logger.info("unregistering actor", actor=actor)
        del self.actors[actor]

    async def send(self, target: URIRef, message: Message):
        """Helper method to send messages between actors"""
        if target in self.actors:
            await self.actors[target].send(message)
        else:
            logger.warning(
                "attempted to send message to non-existent actor",
                target=target,
            )

    async def run_actor[Param](
        self,
        actor_type: type["Actor[Param]"],
        param: Param,
    ):
        app = actor_type(self, param)
        await app()


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

    # You could also include offset/length for partial reads, etc.


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
    async def run(self, context: ActorContext):
        request = await read_http_request(
            self.param.scope, self.param.receive, self.param.target
        )

        request_model = ActorHttpRequest(
            request=request,
            response=context.actor,
        )

        await context.send_model(self.param.target, request_model)
        try:
            response = await context.receive_model(HttpResponseData)
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


@dataclass
class ASGIContext:
    scope: Scope
    receive: Receive
    send: Send


class RootActor(Actor[ASGIContext]):
    """
    The root actor that handles messages from the websocket or HTTP requests.
    """

    async def run(self, context: ActorContext):
        #        await context.spawn(FilesystemActor, trio.Path("vocab"))
        while True:
            try:
                message = await context.receive()
                await self.handle_message(message, context)
            except trio.Cancelled:
                return

    async def handle_message(self, message: Message, context: ActorContext):
        if message["type"] == "http.request":
            request = ActorHttpRequest.model_validate(message)
            await self.handle_http_request(request, context)

    async def handle_http_request(
        self,
        request: ActorHttpRequest,
        context: ActorContext,
    ):
        response = HttpResponseData(
            status=200,
            headers={"Content-Type": "text/plain"},
            body=b"Hello from the root actor!",
        )
        await context.send(request.response, response.model_dump())


class LifespanActor(Actor[ASGIContext]):
    """
    An actor that handles the lifespan of the application.
    """

    async def run(self, context: ActorContext):
        try:
            await context.spawn(RootActor, self.param)
            while True:
                message = await self.param.receive()
                logger.info("lifespan message", message=message)
                if message["type"] == "lifespan.shutdown":
                    await self.param.send(
                        {"type": "lifespan.shutdown.complete"}
                    )
                    return
                elif message["type"] == "lifespan.startup":
                    await self.param.send(
                        {"type": "lifespan.startup.complete"}
                    )
        except* Exception as e:
            logger.error("lifespan failed", error=str(e))
            raise
        finally:
            logger.info("lifespan actor completed")


class DIDDocumentMiddleware:
    """
    Middleware that handles DID document requests.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if (
            scope["type"] == "http"
            and scope["path"] == "/.well-known/did.json"
        ):
            host = dict(scope["headers"]).get(b"host", b"").decode("utf-8")
            host = host.removeprefix("https://").removesuffix("/")
            did = f"did:web:{host}"
            document = {
                "@context": ["https://www.w3.org/ns/did/v1"],
                "id": did,
                "verificationMethod": [],
            }
            logger.info(
                "responding to DID document request", document=document
            )
            response = JSONResponse(document)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


async def main_app(
    scope: Scope,
    receive: Receive,
    send: Send,
    town: Town,
):
    """
    The main application callable (ASGI) handling lifespan, DID document requests,
    actor websockets, and HTTP requests destined for actors.
    """

    context = ASGIContext(scope, receive, send)

    if scope["type"] == "lifespan":
        try:
            await town.run_actor(LifespanActor, context)
        except BaseExceptionGroup as e:
            logger.info("lifespan failed", error=e)

        finally:
            logger.info("lifespan completed")

    elif scope["type"] == "http":
        path = scope["path"]
        target = URIRef(f"{town.base_url}{path}")
        if target in town.actors:
            await town.run_actor(
                RequestHandlingActor,
                HTTPRequestContext(scope, receive, send, target),
            )
        else:
            logger.warning("target actor not found", target=target)
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

    hostname = base_url.replace("https://", "").rstrip("/")
    cert_path, key_path = generate_self_signed_cert(hostname)

    config = create_http_server_config(bind, cert_path, key_path)

    async with trio.open_nursery() as nursery:
        verification_app = Starlette(debug=True)
        verification_app.add_middleware(DIDDocumentMiddleware)
        nursery.start_soon(serve_app, verification_app, config)

        try:
            await verify_base_url(base_url, cert_path, key_path)
        except Exception as e:
            logger.error(
                "failed to verify control over base URL", error=str(e)
            )
            raise RuntimeError(f"Failed to verify base URL {base_url}: {e}")
        finally:
            nursery.cancel_scope.cancel()

    town = Town(base_url)

    async def app(scope: Scope, receive: Receive, send: Send):
        try:
            return await main_app(scope, receive, send, town)
        except* Exception as e:
            logger.info("main app failed", error=str(e))
            raise

    # Wrap the main app with the DID document middleware
    return DIDDocumentMiddleware(app)


def create_http_server_config(bind, cert_path, key_path):
    config = hypercorn.Config()
    config.bind = [bind]
    config.certfile = cert_path
    config.keyfile = key_path
    config.log.error_logger = logger.bind(name="hypercorn.error")
    return config
