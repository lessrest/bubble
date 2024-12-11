import json
import uuid
import pathlib

from io import BytesIO
from base64 import b64encode
from typing import (
    Any,
    Set,
    Dict,
    List,
    Callable,
    Optional,
    Awaitable,
    Generator,
    AsyncGenerator,
    MutableMapping,
)
from datetime import UTC, datetime
from operator import itemgetter
from contextlib import asynccontextmanager, contextmanager
from collections import defaultdict
from dataclasses import dataclass

import trio
import tenacity
import structlog

from rdflib import (
    RDF,
    XSD,
    Graph,
    URIRef,
    Dataset,
    Literal,
    Namespace,
)
from fastapi import (
    Body,
    Form,
    FastAPI,
    Request,
    Response,
    WebSocket,
    HTTPException,
    WebSocketDisconnect,
)
from rdflib.graph import QuotedGraph
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from swash import Parameter, mint, rdfa, vars
from swash.html import HypermediaResponse, tag, attr, html, text, document
from swash.json import pyld
from swash.prfx import NT, DID, DEEPGRAM
from swash.rdfa import rdf_resource, get_subject_data
from swash.util import S, add, new, get_single_subject
from bubble.icon import favicon
from bubble.page import base_html
from bubble.repo import BubbleRepo, using_bubble, current_bubble

logger = structlog.get_logger(__name__)


@dataclass
class ActorContext:
    boss: URIRef
    addr: URIRef
    send: trio.MemorySendChannel
    recv: trio.MemoryReceiveChannel
    trap: bool = False
    name: str = "anonymous"


def fresh_uri(site: Optional[Namespace] = None) -> URIRef:
    if site is None:
        site = hub.get().site
    return mint.fresh_uri(site)


def new_context(parent: URIRef, name: str = "unnamed") -> ActorContext:
    chan_send, chan_recv = trio.open_memory_channel(8)
    return ActorContext(
        parent, fresh_uri(), chan_send, chan_recv, name=name
    )


def root_context(site: Namespace, name: str = "root") -> ActorContext:
    uri = fresh_uri(site)
    chan_send, chan_recv = trio.open_memory_channel(8)
    return ActorContext(uri, uri, chan_send, chan_recv, name=name)


class Town:
    site: Namespace
    curr: Parameter[ActorContext]
    deck: MutableMapping[URIRef, ActorContext]
    yell: structlog.stdlib.BoundLogger

    def __init__(
        self,
        site: str,
        yell: structlog.stdlib.BoundLogger,
    ):
        self.site = Namespace(site)
        self.yell = yell.bind(site=site)

        root = root_context(self.site)
        self.curr = Parameter("current_actor", root)
        self.deck = {root.addr: root}

    def this(self) -> URIRef:
        return self.curr.get().addr

    async def spawn(
        self,
        crib: trio.Nursery,
        code: Callable[..., Awaitable[None]],
        *args,
        name: Optional[str] = None,
    ) -> URIRef:
        if name is None:
            if hasattr(code, "__name__"):
                name = code.__name__
            else:
                name = code.__class__.__name__

        parent_ctx = self.curr.get()
        context = new_context(parent_ctx.addr, name=name)
        self.deck[context.addr] = context

        self.yell.info(
            "spawning",
            actor=context.addr,
            actor_name=name,
            parent=parent_ctx.addr,
        )

        async def task():
            with self.curr.bind(context):
                try:
                    await code(*args)
                    self.yell.info(
                        "actor finished",
                        actor=context.addr,
                        actor_name=name,
                    )
                except BaseException as e:
                    logger.error(
                        "actor crashed",
                        actor=context.addr,
                        actor_name=name,
                        error=e,
                        parent=context.boss,
                    )

                    if parent_ctx and parent_ctx.trap:
                        self.yell.info(
                            "sending exit signal",
                            to=parent_ctx.addr,
                        )
                        await self.send_exit_signal(
                            parent_ctx.addr, context.addr, e
                        )
                    else:
                        self.yell.info("raising exception")
                        raise
                finally:
                    self.yell.info(
                        "deleting actor", actor=(context.addr, name)
                    )
                    del self.deck[context.addr]
                    self.print_actor_tree()

        crib.start_soon(task)
        return context.addr

    async def send_exit_signal(
        self, parent: URIRef, child: URIRef, error: BaseException
    ):
        with with_transient_graph() as id:
            new(
                NT.Exit,
                {NT.actor: child, NT.message: Literal(str(error))},
                id,
            )

            child_ctx = self.deck.get(child)
            child_name = child_ctx.name if child_ctx else "unknown"
            self.yell.info(
                "sending exit signal",
                to=parent,
                child=child,
                child_name=child_name,
                error=error,
            )

            await self.send(parent)

    async def send(self, actor: URIRef, message: Optional[Graph] = None):
        if message is None:
            message = vars.graph.get()

        if actor not in self.deck:
            raise ValueError(f"Actor {actor} not found")

        await self.deck[actor].send.send(message)

    def get_actor_hierarchy(self) -> Dict[URIRef, Set[URIRef]]:
        """Get the parent-child relationships between actors."""
        kids = defaultdict(set)
        for addr, ctx in self.deck.items():
            if ctx.boss != ctx.addr:  # Skip root which is its own parent
                kids[ctx.boss].add(addr)
        return dict(kids)

    def format_actor_tree(
        self, root: URIRef, indent: str = "", is_last: bool = True
    ) -> str:
        """Format the actor hierarchy as a tree string starting from given root."""
        ctx = self.deck.get(root)
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
            uri for uri, ctx in self.deck.items() if ctx.boss == ctx.addr
        )
        tree = self.format_actor_tree(root)
        self.yell.info("Actor hierarchy:\n" + tree)


hub = Parameter[Town]("hub")


def this() -> URIRef:
    return hub.get().this()


async def spawn(
    nursery: trio.Nursery,
    action: Callable,
    *args,
    name: Optional[str] = None,
):
    system = hub.get()
    return await system.spawn(nursery, action, *args, name=name)


async def send(actor: URIRef, message: Optional[Graph] = None):
    system = hub.get()
    if message is None:
        message = vars.graph.get()
    logger.info("sending message", actor=actor, graph=message)
    return await system.send(actor, message)


async def receive() -> Graph:
    system = hub.get()
    return await system.curr.get().recv.receive()


class ServerActor[State]:
    def __init__(self, state: State, name: Optional[str] = None):
        self.state = state
        self.name = name or self.__class__.__name__
        self.stop = False

    async def __call__(self):
        """Main actor message processing loop with error handling."""
        async with trio.open_nursery() as nursery:
            try:
                await self.init()
                while not self.stop:
                    msg = await receive()
                    logger.info("received message", graph=msg)
                    response = await self.handle(nursery, msg)
                    logger.info("sending response", graph=response)

                    for reply_to in msg.objects(msg.identifier, NT.replyTo):
                        await send(URIRef(reply_to), response)
            except Exception as e:
                logger.error("actor message handling error", error=e)
                raise

    async def init(self):
        pass

    async def handle(self, nursery: trio.Nursery, graph: Graph) -> Graph:
        raise NotImplementedError


logger = structlog.get_logger()


class SimpleSupervisor:
    def __init__(self, actor: Callable):
        self.actor = actor

    async def __call__(self):
        async with with_new_transaction():
            new(NT.Supervisor, {}, this())

        def retry_sleep(retry_state: tenacity.RetryCallState) -> Any:
            return logger.warning(
                "supervised actor tree crashed; retrying after exponential backoff",
                retrying=retry_state,
            )

        retry = tenacity.AsyncRetrying(
            wait=tenacity.wait_exponential(multiplier=1, max=60),
            retry=tenacity.retry_if_exception_type(
                (trio.Cancelled, BaseExceptionGroup)
            ),
            before_sleep=retry_sleep,
        )

        async for attempt in retry:
            with attempt:
                async with trio.open_nursery() as nursery:
                    logger.info("starting supervised actor tree")
                    child = await spawn(nursery, self.actor)
                    add(this(), {NT.supervises: child})


async def call(actor: URIRef, payload: Optional[Graph] = None) -> Graph:
    if payload is None:
        payload = vars.graph.get()

    sendchan, recvchan = trio.open_memory_channel[Graph](1)

    tmp = fresh_uri()
    hub.get().deck[tmp] = ActorContext(
        boss=this(), addr=tmp, send=sendchan, recv=recvchan
    )

    payload.add((payload.identifier, NT.replyTo, tmp))

    logger.info(
        "sending request",
        actor=actor,
        graph=payload,
    )

    await send(actor, payload)

    return await recvchan.receive()


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


@asynccontextmanager
async def with_new_transaction(graph: Optional[Graph] = None):
    """Create a new transaction with a fresh graph that will be persisted."""
    g = create_graph()
    if graph is not None:
        g += graph

    with vars.graph.bind(g):
        yield g

    logger.info("persisting transaction", graph=g)

    await persist(g)


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


async def persist(graph: Graph):
    """Persist a graph to the current bubble."""
    bubble = current_bubble.get()
    before_count = len(bubble.graph)
    bubble.graph += graph
    after_count = len(bubble.graph)

    await bubble.save_graph()

    logger.info(
        "persisted graph",
        before=before_count,
        after=after_count,
        added=after_count - before_count,
        bubble_graph=bubble.graph,
        graph=graph,
    )


#    print_n3(current_bubble.get().graph, "current_bubble.get().graph")
#    print_n3(vars.graph.get(), "vars.graph.get()")
#    print_n3(graph, "graph")


def get_site() -> Namespace:
    """Get the site namespace from the current actor system."""
    return hub.get().site


def get_base() -> URIRef:
    """Get the base URI from the current actor system."""
    return hub.get().site[""]


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
        self.site = Namespace(base_url)
        self.yell = structlog.get_logger(__name__).bind(bind=bind)
        self.app = FastAPI()

        self._setup_error_handlers()
        self._setup_middleware()
        self._setup_routes()

        self.system = Town(str(self.site), self.yell)
        hub.set(self.system)

        # Add session tracking
        self.websocket_sessions: Dict[str, WebSocket] = {}
        self.session_actors: Dict[str, URIRef] = {}
        self.actor_sessions: Dict[URIRef, str] = {}

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
                directory=str(pathlib.Path(__file__).parent / "static")
            ),
        )

        self.app.get("/favicon.ico")(self.favicon)
        self.app.get("/health")(self.health_check)
        self.app.get("/.well-known/did.json")(self.get_did_document)
        self.app.get("/graphs")(graphs_view)
        self.app.get("/graph")(graph_view)
        self.app.get("/")(self.root)

        self.app.get("/{id}")(self.actor_get)

        self.app.post("/{id}/message")(self.actor_message)
        self.app.post("/{id}")(self.actor_post)
        self.app.put("/{id}")(self.actor_put)

        self.app.websocket("/{id}/upload")(self.ws_upload)
        self.app.websocket("/{id}/jsonld")(self.ws_jsonld)

    async def health_check(self):
        with with_transient_graph("health") as id:
            generate_health_status(id)
            return JSONLinkedDataResponse()

    async def get_did_document(self):
        did_uri = URIRef(
            str(self.site).replace("https://", "did:web:").rstrip("/")
        )

        with with_transient_graph(".well-known/did.json") as id:
            build_did_document(did_uri, id)
            return JSONLinkedDataResponse(vocab=DID)

    async def actor_message(self, id: str, type: str = Form(...)):
        actor = self.site[id]
        async with with_new_transaction() as g:
            record_message(type, actor, g)
            result = await call(actor, g)
            return LinkedDataResponse(result)

    # Middleware
    async def bind_document(self, request, call_next):
        with document():
            return await call_next(request)

    async def bind_actor_system(self, request, call_next):
        with hub.bind(self.system):
            return await call_next(request)

    async def bind_bubble(self, request, call_next):
        with using_bubble(self.repo):
            self.repo.dataset.bind("site", self.site)
            return await call_next(request)

    # Route handlers
    async def all_exception_handler(self, request: Request, exc: Exception):
        self.yell.error("Unhandled exception", error=exc)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal Server Error", "details": str(exc)},
        )

    async def favicon(self):
        img = await favicon()
        ico_buffer = BytesIO()
        img.save(ico_buffer, format="ICO")
        ico_data = ico_buffer.getvalue()

        return Response(content=ico_data, media_type="image/x-icon")

    async def actor_post(self, id: str, body: dict = Body(...)):
        actor = self.site[id]
        async with with_new_transaction() as g:
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
        actor = hub.get().deck[self.site[id]]

        async def stream_messages():
            try:
                while True:
                    try:
                        graph: Graph = await actor.recv.receive()
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

    # Add uptime actor URI to the HTML template
    async def root(self):
        session_id = self._generate_session_id()

        with base_html("Bubble"):
            # with tag("jsonld-socket"):
            #     attr(
            #         "endpoint",
            #         f"{self.get_websocket_base()}{session_id}/jsonld",
            #     )
            #     attr("uptime-target", str(uptime_actor))
            with tag("main", classes="flex flex-col gap-4 p-4"):
                rdf_resource(self.base)
        return HypermediaResponse()

    def get_websocket_base(self):
        return self.base_url.replace("https://", "wss://")

    async def ws_jsonld(self, websocket: WebSocket, id: str):
        """WebSocket handler for JSON-LD messages with session management."""
        session_id = self._generate_session_id()

        try:
            await websocket.accept()
            self.websocket_sessions[session_id] = websocket
            logger.info(
                "starting jsonld websocket connection",
                session_id=session_id,
            )

            # Create an actor for this session
            session_actor = mint.fresh_uri(self.site)
            self.session_actors[session_id] = session_actor
            self.actor_sessions[session_actor] = session_id

            while True:
                try:
                    data = await websocket.receive_json()
                    logger.info(
                        "received json-ld message",
                        data=data,
                        session=session_id,
                    )

                    # Create a graph from the JSON-LD message
                    g = Graph(identifier=data["@id"])
                    g.parse(data=json.dumps(data), format="json-ld")

                    # Add session actor as source
                    g.add((g.identifier, NT.source, session_actor))

                    logger.info("parsed json-ld message", graph=g)

                    # Find target actor and send message
                    target = list(g.objects(g.identifier, NT.target))
                    if target:
                        response = await call(URIRef(target[0]), g)
                        await websocket.send_json(
                            json.loads(response.serialize(format="json-ld"))
                        )
                    else:
                        await websocket.send_json(
                            {"error": "No target actor specified"}
                        )

                except WebSocketDisconnect as e:
                    logger.error("websocket disconnect", error=e)
                    break

                except Exception as e:
                    logger.error(
                        "error processing websocket message",
                        error=e,
                        session=session_id,
                    )
                    await websocket.send_json({"error": str(e)})

        except Exception as e:
            logger.error(
                "websocket handler error", error=e, session=session_id
            )
            try:
                await websocket.close(code=1011, reason=str(e))
            except Exception:
                pass
        finally:
            # Clean up session
            if session_id in self.session_actors:
                actor = self.session_actors[session_id]
                del self.actor_sessions[actor]
                del self.session_actors[session_id]
            if session_id in self.websocket_sessions:
                del self.websocket_sessions[session_id]
            await websocket.close()

    @contextmanager
    def install_context(self):
        """Install the actor system and bubble context for request handling."""
        with hub.bind(self.system):
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
            async with with_new_transaction() as g:
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

    def _generate_session_id(self) -> str:
        """Generate a random session ID for WebSocket connections."""
        return str(uuid.uuid4())

    async def send_to_client(
        self, actor_uri: URIRef, message: Graph
    ) -> bool:
        """Send a message to a client if it's connected."""
        session_id = self.actor_sessions.get(actor_uri)
        if not session_id:
            logger.warning("No session found for actor", actor=actor_uri)
            return False

        websocket = self.websocket_sessions.get(session_id)
        if not websocket:
            logger.warning(
                "No websocket found for session", session=session_id
            )
            return False

        try:
            await websocket.send_json(
                json.loads(message.serialize(format="json-ld"))
            )
            return True
        except Exception as e:
            logger.error(
                "Error sending message to client",
                error=e,
                session=session_id,
                actor=actor_uri,
            )
            return False


@contextmanager
def in_request_graph(g: Graph):
    with vars.graph.bind(g):
        yield g


def town_app(
    base_url: str, bind: str, repo: BubbleRepo, root_actor=None
) -> FastAPI:
    """Create and return a FastAPI app for the town."""
    app = TownApp(base_url, bind, repo)
    return app.get_fastapi_app()


def count_outbound_links(graph: Graph, node: S) -> int:
    """Count outbound links from a node, excluding rdf:type."""
    return len([p for p in graph.predicates(node) if p != RDF.type])


def get_traversal_order(graph: Graph) -> List[S]:
    """Get nodes in traversal order - prioritizing named resources with fewer outbound links."""
    # Count outbound links for each subject
    link_counts = {
        subject: count_outbound_links(graph, subject)
        for subject in graph.subjects()
    }

    # Group nodes by type (URIRef vs BNode)
    typed_nodes = defaultdict(list)
    for node in link_counts:
        if isinstance(node, URIRef):
            typed_nodes["uri"].append(node)
        else:
            typed_nodes["bnode"].append(node)

    # Sort each group by number of outbound links
    sorted_nodes = []

    # URIRefs first, sorted by link count
    sorted_nodes.extend(
        sorted(typed_nodes["uri"], key=lambda x: link_counts[x])
    )

    # Then BNodes, sorted by link count
    sorted_nodes.extend(
        sorted(typed_nodes["bnode"], key=lambda x: link_counts[x])
    )

    return sorted_nodes


def render_graph_view(graph: Graph) -> None:
    """Render a complete view of a graph with smart traversal ordering."""
    nodes = get_traversal_order(graph)

    with tag("div", classes="flex flex-col gap-4"):
        # First pass - render all nodes that have an rdf:type
        for node in nodes:
            types = list(graph.objects(node, RDF.type))
            if types:
                with tag("div", classes="border-l-4 border-blue-500 pl-2"):
                    data = get_subject_data(graph, node, context=graph)
                    rdf_resource(node, data)

        # Second pass - render remaining nodes
        remaining = [
            n for n in nodes if not list(graph.objects(n, RDF.type))
        ]
        if remaining:
            with tag(
                "div",
                classes="mt-4 border-t border-gray-300 dark:border-gray-700 pt-4",
            ):
                with tag(
                    "h3",
                    classes="text-lg font-semibold mb-2 text-gray-600 dark:text-gray-400",
                ):
                    text("Additional Resources")
                for node in remaining:
                    with tag(
                        "div", classes="border-l-4 border-gray-500 pl-2"
                    ):
                        data = get_subject_data(graph, node, context=graph)
                        rdf_resource(node, data)


def render_graphs_overview(dataset: Dataset) -> None:
    """Render an overview of all graphs in the dataset."""
    with tag("div", classes="p-4 flex flex-col gap-6"):
        with tag(
            "h2",
            classes="text-2xl font-bold text-gray-800 dark:text-gray-200",
        ):
            text("Available Graphs")

        with tag("div", classes="grid gap-4"):
            # Get all non-formula graphs and sort by triple count (largest first)
            graphs = [
                g
                for g in dataset.graphs()
                if not isinstance(g, QuotedGraph)
            ]

            for graph in sorted(graphs, key=len, reverse=True):
                render_graph_summary(graph)


def render_graph_summary(graph: Graph) -> None:
    """Render a summary card for a single graph."""
    subject_count = len(set(graph.subjects()))
    triple_count = len(graph)

    with tag(
        "div",
        classes="border rounded-lg p-4 bg-white dark:bg-gray-800 shadow-sm hover:shadow-md transition-shadow",
    ):
        # Header with graph ID and stats
        with tag("div", classes="flex justify-between items-start mb-4"):
            # Graph ID as link
            with tag(
                "a",
                href=f"/graph?graph={str(graph.identifier)}",
                classes="text-lg font-medium text-blue-600 dark:text-blue-400 hover:underline",
            ):
                text(str(graph.identifier))

            # Stats
            with tag(
                "div", classes="text-sm text-gray-500 dark:text-gray-400"
            ):
                text(f"{subject_count} subjects, {triple_count} triples")

        # Preview of typed resources
        typed_subjects = {s for s in graph.subjects(RDF.type, None)}
        if typed_subjects:
            with tag("div", classes="mt-2"):
                with tag(
                    "h4",
                    classes="text-sm font-medium text-gray-600 dark:text-gray-400 mb-2",
                ):
                    text("Resource Types")

                type_counts = defaultdict(int)
                for s in typed_subjects:
                    for t in graph.objects(s, RDF.type):
                        type_counts[t] += 1

                with tag("div", classes="flex flex-wrap gap-2"):
                    for rdf_type, count in sorted(
                        type_counts.items(),
                        key=lambda x: (-x[1], str(x[0])),
                    ):
                        with tag(
                            "span",
                            classes="px-2 py-1 text-xs rounded-full bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200",
                        ):
                            text(
                                f"{str(rdf_type).split('#')[-1].split('/')[-1]} ({count})"
                            )


@html.div("min-h-screen bg-gray-50 dark:bg-gray-900")
def graphs_view(request: Request):
    """Handler for viewing all graphs in the bubble."""
    bubble = current_bubble.get()
    with base_html("Graphs"):
        render_graphs_overview(bubble.dataset)
        return HypermediaResponse()


@html.div("p-4")
def graph_view(request: Request):
    """Handler for viewing complete graphs."""
    graph_id = request.query_params.get("graph")
    if not graph_id:
        raise HTTPException(status_code=400, detail="No graph ID provided")

    graph = None
    bubble = current_bubble.get()

    # Try to find the graph in the bubble's dataset
    for g in bubble.dataset.graphs():
        if str(g.identifier) == graph_id:
            graph = g
            break

    if not graph:
        raise HTTPException(status_code=404, detail="Graph not found")

    with base_html("Graph"):
        render_graph_view(graph)
        return HypermediaResponse()
