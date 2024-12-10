import json
import pathlib

from base64 import b64encode
from typing import (
    Dict,
    Callable,
    Optional,
    Awaitable,
    Generator,
    AsyncGenerator,
    MutableMapping,
    Set,
)
from datetime import UTC, datetime
from contextlib import contextmanager
from dataclasses import dataclass
from collections import defaultdict

import trio
import structlog
import importhook

from rdflib import RDF, XSD, Graph, URIRef, Literal, Namespace
from fastapi import Body, Form, FastAPI, Request, Response, WebSocket
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from swash import Parameter, mint, rdfa, vars
from swash.html import HypermediaResponse, document
from swash.prfx import NT, DID, DEEPGRAM
from swash.rdfa import rdf_resource
from swash.util import S, new
from bubble.page import base_html
from bubble.repo import BubbleRepo, using_bubble, current_bubble


@importhook.on_import("aiohttp")  # type: ignore
def on_aiohttp_import(aiohttp):
    # This is a hack to avoid PyLD crashing on load in IPython.
    raise ImportError("hehe")


try:
    import pyld
finally:
    pass

logger = structlog.get_logger(__name__)


@dataclass
class ActorContext:
    parent: URIRef
    uri: URIRef
    chan_send: trio.MemorySendChannel
    chan_recv: trio.MemoryReceiveChannel
    trap_exit: bool = False
    name: str = "unnamed"


def new_context(parent: URIRef, name: str = "unnamed") -> ActorContext:
    site = current_actor_system.get().site
    uri = mint.fresh_uri(site)
    chan_send, chan_recv = trio.open_memory_channel(8)
    return ActorContext(parent, uri, chan_send, chan_recv, name=name)


def root_context(site: Namespace, name: str = "root") -> ActorContext:
    uri = mint.fresh_uri(site)
    chan_send, chan_recv = trio.open_memory_channel(8)
    return ActorContext(uri, uri, chan_send, chan_recv, name=name)


class ActorSystem:
    site: Namespace
    current_actor: Parameter[ActorContext]
    actors: MutableMapping[URIRef, ActorContext]
    logger: structlog.stdlib.BoundLogger

    def __init__(
        self,
        site: str,
        logger: structlog.stdlib.BoundLogger,
    ):
        self.site = Namespace(site)
        self.logger = logger.bind(site=site)

        root = root_context(self.site)
        self.current_actor = Parameter("current_actor", root)
        self.actors = {root.uri: root}

    def this(self) -> URIRef:
        return self.current_actor.get().uri

    async def spawn(
        self,
        nursery: trio.Nursery,
        action: Callable[..., Awaitable[None]],
        *args,
        name: Optional[str] = None,
    ) -> URIRef:
        if name is None:
            if hasattr(action, "__name__"):
                name = action.__name__
            else:
                name = action.__class__.__name__

        parent_ctx = self.current_actor.get()
        context = new_context(parent_ctx.uri, name=name)
        self.actors[context.uri] = context

        self.logger.info(
            "spawning",
            actor=context.uri,
            actor_name=name,
            parent=parent_ctx.uri,
        )

        async def task():
            with self.current_actor.bind(context):
                try:
                    await action(*args)
                    self.logger.info(
                        "actor finished", actor=context.uri, actor_name=name
                    )
                except BaseException as e:
                    logger.error(
                        "actor crashed",
                        actor=context.uri,
                        actor_name=name,
                        error=e,
                        parent=context.parent,
                    )

                    if parent_ctx and parent_ctx.trap_exit:
                        self.logger.info(
                            "sending exit signal",
                            to=parent_ctx.uri,
                        )
                        await self.send_exit_signal(
                            parent_ctx.uri, context.uri, e
                        )
                    else:
                        self.logger.info("raising exception")
                        raise
                finally:
                    self.logger.info(
                        "deleting actor", actor=(context.uri, name)
                    )
                    del self.actors[context.uri]
                    self.print_actor_tree()

        nursery.start_soon(task)
        return context.uri

    async def send_exit_signal(
        self, parent: URIRef, child: URIRef, error: BaseException
    ):
        g = create_graph()
        g.add((g.identifier, RDF.type, NT.Exit))
        g.add((g.identifier, NT.actor, child))
        g.add((g.identifier, NT.message, Literal(str(error))))
        child_ctx = self.actors.get(child)
        child_name = child_ctx.name if child_ctx else "unknown"
        self.logger.info(
            "sending exit signal",
            to=parent,
            child=child,
            child_name=child_name,
            error=error,
        )
        await self.send(parent, g)

    async def send(self, actor: URIRef, message: Graph):
        if actor not in self.actors:
            raise ValueError(f"Actor {actor} not found")
        await self.actors[actor].chan_send.send(message)

    def get_actor_hierarchy(self) -> Dict[URIRef, Set[URIRef]]:
        """Get the parent-child relationships between actors."""
        children = defaultdict(set)
        for actor_uri, ctx in self.actors.items():
            if ctx.parent != ctx.uri:  # Skip root which is its own parent
                children[ctx.parent].add(actor_uri)
        return dict(children)

    def format_actor_tree(
        self, root: URIRef, indent: str = "", is_last: bool = True
    ) -> str:
        """Format the actor hierarchy as a tree string starting from given root."""
        ctx = self.actors.get(root)
        if not ctx:
            return f"{indent}[deleted actor {root}]\n"

        marker = "└── " if is_last else "├── "
        result = f"{indent}{marker}{ctx.name} ({root})\n"

        children = self.get_actor_hierarchy().get(root, set())
        child_list = sorted(children)  # Sort for consistent output

        for i, child in enumerate(child_list):
            is_last_child = i == len(child_list) - 1
            next_indent = indent + ("    " if is_last else "│   ")
            result += self.format_actor_tree(
                child, next_indent, is_last_child
            )

        return result

    def print_actor_tree(self):
        """Print the complete actor hierarchy tree."""
        # Find the root (actor that is its own parent)
        root = next(
            uri for uri, ctx in self.actors.items() if ctx.parent == ctx.uri
        )
        tree = self.format_actor_tree(root)
        self.logger.info("Actor hierarchy:\n" + tree)


current_actor_system = Parameter[ActorSystem]("current_actor_system")


def this() -> URIRef:
    return current_actor_system.get().this()


async def spawn(
    nursery: trio.Nursery,
    action: Callable,
    *args,
    name: Optional[str] = None,
):
    system = current_actor_system.get()
    return await system.spawn(nursery, action, *args, name=name)


async def send(actor: URIRef, message: Optional[Graph] = None):
    system = current_actor_system.get()
    if message is None:
        message = vars.graph.get()
    logger.info("sending message", actor=actor, graph=message)
    return await system.send(actor, message)


async def receive() -> Graph:
    system = current_actor_system.get()
    return await system.current_actor.get().chan_recv.receive()


class ServerActor[State]:
    def __init__(self, state: State, name: Optional[str] = None):
        self.state = state
        self.name = name or self.__class__.__name__

    async def __call__(self):
        """Main actor message processing loop with error handling."""
        try:
            async with trio.open_nursery() as nursery:
                await self.init()
                while True:
                    msg = await receive()
                    logger.info("received message", graph=msg)
                    response = await self.handle(nursery, msg)
                    logger.info("sending response", graph=response)

                    for reply_to in msg.objects(msg.identifier, NT.replyTo):
                        await send(URIRef(reply_to), response)
        except Exception as e:
            logger.error("actor message handling error", error=e)
            raise  # Let it crash

    async def init(self):
        pass

    async def handle(self, nursery: trio.Nursery, graph: Graph) -> Graph:
        raise NotImplementedError


async def call(actor: URIRef, payload: Optional[Graph] = None) -> Graph:
    if payload is None:
        payload = vars.graph.get()

    send_chan, recv_chan = trio.open_memory_channel[Graph](1)

    tmp = mint.fresh_uri(get_site())
    current_actor_system.get().actors[tmp] = ActorContext(
        parent=this(), uri=tmp, chan_send=send_chan, chan_recv=recv_chan
    )

    payload.add((payload.identifier, NT.replyTo, tmp))

    logger.info(
        "sending request",
        actor=actor,
        graph=payload,
    )

    await send(actor, payload)

    return await recv_chan.receive()


def create_graph(
    suffix: Optional[str] = None, *, base: Optional[str] = None
) -> Graph:
    """Create a new graph with standard bindings and optional suffix-based identifier.

    Args:
        suffix: Optional path suffix for the graph ID. If None, a fresh URI is minted.
        base: Optional base URI. If None, uses the current site.
    """
    site = get_site()
    base = base or str(site)

    if suffix is None:
        id = mint.fresh_uri(site)
    else:
        id = site[suffix]

    g = Graph(base=base, identifier=id)
    g.bind("nt", NT)
    g.bind("deepgram", DEEPGRAM)
    g.bind("site", site)
    return g


@contextmanager
def with_new_transaction(graph: Optional[Graph] = None):
    """Create a new transaction with a fresh graph that will be persisted."""
    g = create_graph()
    if graph is not None:
        g += graph

    with vars.graph.bind(g):
        yield g
    logger.info("persisting transaction", graph=g)
    persist(g)


@contextmanager
def with_transient_graph(
    suffix: Optional[str] = None,
) -> Generator[URIRef, None, None]:
    """Create a temporary graph that won't be persisted."""
    g = create_graph(suffix)
    with vars.graph.bind(g):
        assert isinstance(g.identifier, URIRef)
        yield g.identifier


class LinkedDataResponse(HypermediaResponse):
    def __init__(
        self,
        graph: Optional[Graph] = None,
        *,
        vocab: Optional[Namespace] = None,
        context: Optional[Dict] = None,
        status_code: int = 200,
        headers: Optional[Dict[str, str]] = None,
    ):
        if graph is None:
            graph = vars.graph.get()

        if headers is None:
            headers = {}

        headers["Link"] = f'<{str(graph.identifier)}>; rel="self"'

        with base_html("Bubble"):
            rdf_resource(graph.identifier)

        super().__init__(
            status_code=status_code,
            headers=headers,
        )


class JSONLinkedDataResponse(JSONResponse):
    def __init__(
        self,
        graph: Optional[Graph] = None,
        *,
        vocab: Optional[Namespace] = None,
        context: Optional[Dict] = None,
        status_code: int = 200,
        headers: Optional[Dict[str, str]] = None,
    ):
        if graph is None:
            graph = vars.graph.get()

        if context is None:
            context = {
                "nt": str(NT),
                "w3": "https://www.w3.org/ns/",
                "@base": str(graph.base),
            }

        if vocab is not None:
            context["@vocab"] = str(vocab)

        jsonld = json.loads(graph.serialize(format="json-ld"))
        compacted = pyld.jsonld.compact(
            jsonld, context, {"base": str(graph.base)}
        )

        if headers is None:
            headers = {}

        headers["Content-Type"] = "application/ld+json"
        headers["Link"] = f'<{str(graph.identifier)}>; rel="self"'

        super().__init__(
            content=compacted,
            status_code=status_code,
            headers=headers,
            media_type="application/ld+json",
        )


def persist(graph: Graph):
    """Persist a graph to the current bubble."""
    current_bubble.get().graph += graph


def get_site() -> Namespace:
    """Get the site namespace from the current actor system."""
    return current_actor_system.get().site


def record_message(type: str, actor: URIRef, g: Graph):
    """Record a message in the graph."""
    new(
        URIRef(type),
        {
            NT.created: Literal(
                datetime.now(UTC).isoformat(), datatype=XSD.dateTime
            ),
            NT.target: actor,
        },
        g.identifier,
    )


def generate_health_status(id: S):
    """Generate health status information."""
    new(
        NT.HealthCheck,
        {
            NT.status: Literal("ok"),
            NT.actorSystem: this(),
        },
        subject=id,
    )


def build_did_document(did_uri: URIRef, doc_uri: S):
    """Build a DID document."""
    new(
        DID.DIDDocument,
        {
            DID.id: did_uri,
            DID.controller: did_uri,
            DID.created: Literal(
                datetime.now(UTC).isoformat(), datatype=XSD.dateTime
            ),
            DID.verificationMethod: [
                new(
                    DID.Ed25519VerificationKey2020,
                    {DID.controller: did_uri},
                )
            ],
        },
        subject=doc_uri,
    )


class TownApp:
    def __init__(
        self,
        base_url: str,
        bind: str,
        repo: BubbleRepo,
    ):
        self.base_url = base_url
        self.base = URIRef(base_url)
        self.bind = bind
        self.repo = repo
        self.site = Namespace(base_url + "/")
        self.logger = structlog.get_logger(__name__).bind(bind=bind)
        self.app = FastAPI()
        self._setup_error_handlers()
        self._setup_middleware()
        self._setup_routes()

        self.system = ActorSystem(str(self.site), self.logger)
        current_actor_system.set(self.system)

    def _setup_error_handlers(self):
        """Setup comprehensive error handling for the web layer."""

        @self.app.exception_handler(Exception)
        async def handle_generic_error(request: Request, exc: Exception):
            logger.error(
                "unhandled web error", error=exc, path=request.url.path
            )
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal Server Error",
                    "details": str(exc),
                },
            )

    def _setup_middleware(self):
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        self.app.middleware("http")(self.bind_document)
        self.app.middleware("http")(self.bind_actor_system)
        self.app.middleware("http")(self.bind_bubble)

    def _setup_routes(self):
        self.app.include_router(rdfa.router)
        self.app.mount(
            "/static",
            StaticFiles(
                directory=str(
                    pathlib.Path(__file__).parent.parent / "static"
                )
            ),
        )

        # Setup route handlers
        self.app.get("/favicon.ico")(self.favicon)
        self.app.get("/health")(self.health_check)
        self.app.get("/.well-known/did.json")(self.get_did_document)
        self.app.post("/{id}")(self.actor_post)
        self.app.post("/{id}/message")(self.actor_message)
        self.app.put("/{id}")(self.actor_put)
        self.app.websocket("/{id}/upload")(self.ws_upload)
        self.app.get("/{id}")(self.actor_get)
        self.app.get("/")(self.root)

    async def health_check(self):
        with with_transient_graph("health") as id:
            generate_health_status(id)
            return LinkedDataResponse()

    async def get_did_document(self):
        did_uri = URIRef(
            str(self.site).replace("https://", "did:web:").rstrip("/")
        )

        with with_transient_graph(".well-known/did.json") as id:
            build_did_document(did_uri, id)
            return LinkedDataResponse(vocab=DID)

    async def actor_message(self, id: str, type: str = Form(...)):
        actor = self.site[id]
        with with_new_transaction() as g:
            record_message(type, actor, g)
            result = await call(actor, g)
            return LinkedDataResponse(result)

    # Middleware
    async def bind_document(self, request, call_next):
        with document():
            return await call_next(request)

    async def bind_actor_system(self, request, call_next):
        with current_actor_system.bind(self.system):
            return await call_next(request)

    async def bind_bubble(self, request, call_next):
        with using_bubble(self.repo):
            self.repo.dataset.bind("site", self.site)
            return await call_next(request)

    # Route handlers
    async def all_exception_handler(self, request: Request, exc: Exception):
        self.logger.error("Unhandled exception", error=exc)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal Server Error", "details": str(exc)},
        )

    async def favicon(self):
        return Response(status_code=204)

    async def actor_post(self, id: str, body: dict = Body(...)):
        actor = self.site[id]
        with with_new_transaction() as g:
            body["@id"] = str(g.identifier)
            g.parse(data=json.dumps(body), format="json-ld")
            result = await call(actor, g)
            return LinkedDataResponse(result)

    async def actor_put(self, id: str, request: Request):
        actor = self.site[id]

        async def request_stream():
            async for chunk in request.stream():
                yield chunk

        result = await self._handle_upload_stream(actor, request_stream())
        return LinkedDataResponse(result)

    async def ws_upload(self, websocket: WebSocket, id: str):
        """WebSocket handler with proper error handling."""
        try:
            await websocket.accept()
            actor = self.site[id]
            logger.info("starting websocket upload", actor=actor)

            async def receive_messages():
                while True:
                    try:
                        message = await websocket.receive_bytes()
                        yield message
                    except Exception as e:
                        logger.error("websocket receive error", error=e)
                        break

            with self.install_context():
                result = await self._handle_upload_stream(
                    actor, receive_messages()
                )

            await websocket.send_json(result.serialize(format="json-ld"))

        except Exception as e:
            logger.error("websocket handler error", error=e)
            try:
                await websocket.close(code=1011, reason=str(e))
            except Exception:
                pass  # Connection might already be closed
            raise
        finally:
            await websocket.close()

    async def actor_get(self, id: str):
        actor = current_actor_system.get().actors[self.site[id]]

        async def stream_messages():
            try:
                while True:
                    try:
                        graph: Graph = await actor.chan_recv.receive()
                        jsonld = graph.serialize(format="json-ld")
                        yield f"event: message\ndata: {jsonld}\n\n"
                    except (
                        trio.BrokenResourceError,
                        trio.ClosedResourceError,
                    ):
                        break
            except Exception as e:
                logger.error("Error in message stream", error=e)
                return

        return StreamingResponse(
            stream_messages(), media_type="text/event-stream"
        )

    async def root(self):
        with base_html("Bubble"):
            rdf_resource(self.base)
        return HypermediaResponse()

    @contextmanager
    def install_context(self):
        """Install the actor system and bubble context for request handling."""
        with current_actor_system.bind(self.system):
            with using_bubble(self.repo):
                yield

    async def _handle_upload_stream(
        self, actor: URIRef, stream: AsyncGenerator[bytes, None]
    ) -> Graph:
        """Handle upload stream with proper error handling."""
        try:
            async for chunk in stream:
                try:
                    await self._send_chunk_to_actor(actor, chunk)
                except Exception as e:
                    logger.error("chunk processing error", error=e)
                    raise RuntimeError(
                        f"Failed to process chunk: {str(e)}"
                    ) from e

            # Send end marker
            with with_new_transaction() as g:
                new(NT.End, {}, g.identifier)
                await send(actor)

            # Return completion message
            g = create_graph()
            g.add((g.identifier, RDF.type, NT.Done))
            return g

        except Exception as e:
            logger.error("upload stream error", error=e)
            g = create_graph()
            g.add((g.identifier, RDF.type, NT.Error))
            g.add((g.identifier, NT.message, Literal(str(e))))
            return g

    async def _send_chunk_to_actor(
        self, actor: URIRef, message: bytes
    ) -> URIRef:
        with with_transient_graph() as id:
            new(
                NT.Chunk,
                {
                    NT.bytes: Literal(
                        b64encode(message),
                        datatype=XSD.base64Binary,
                    )
                },
                id,
            )
            await send(actor)
        return id

    def get_fastapi_app(self) -> FastAPI:
        return self.app


@contextmanager
def in_request_graph(g: Graph):
    with vars.graph.bind(g):
        yield g.identifier
