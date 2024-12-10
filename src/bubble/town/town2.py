from base64 import b64encode
import json

import pathlib
import sys
from typing import (
    Any,
    Dict,
    Callable,
    Generator,
    Optional,
    Awaitable,
    AsyncGenerator,
    MutableMapping,
)
from datetime import UTC, datetime
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass

from fastapi.staticfiles import StaticFiles
import importhook

from pydantic import BaseModel
from swash import rdfa
from swash.html import HypermediaResponse, document
from swash.rdfa import get_subject_data, rdf_resource
import trio
import structlog

from rdflib import XSD, BNode, Dataset, Graph, URIRef, Literal, Namespace
from fastapi import Body, FastAPI, Form, Request, Response, WebSocket
from fastapi.responses import JSONResponse, StreamingResponse
from trio_websocket import WebSocketConnection

from swash import Parameter, mint, vars
from swash.prfx import DEEPGRAM, NT, DID, RDF
from swash.util import new
from bubble.page import base_html
from bubble.repo import BubbleRepo, using_bubble, current_bubble
from fastapi.middleware.cors import CORSMiddleware


@importhook.on_import("aiohttp")  # type: ignore
def on_aiohttp_import(aiohttp):
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


def new_context(parent: URIRef) -> ActorContext:
    site = current_actor_system.get().site
    uri = mint.fresh_uri(site)
    chan_send, chan_recv = trio.open_memory_channel(8)
    return ActorContext(parent, uri, chan_send, chan_recv)


def root_context(site: Namespace) -> ActorContext:
    uri = mint.fresh_uri(site)
    chan_send, chan_recv = trio.open_memory_channel(8)
    return ActorContext(uri, uri, chan_send, chan_recv)


class ActorSystem:
    site: Namespace
    nursery: trio.Nursery
    current_actor: Parameter[ActorContext]
    actors: MutableMapping[URIRef, ActorContext]
    logger: structlog.stdlib.BoundLogger

    def __init__(
        self,
        site: str,
        nursery: trio.Nursery,
        logger: structlog.stdlib.BoundLogger,
    ):
        self.site = Namespace(site)
        self.nursery = nursery
        self.logger = logger.bind(site=site)

        root = root_context(self.site)

        self.current_actor = Parameter("current_actor", root)
        self.actors = {root.uri: root}

    def this(self) -> URIRef:
        return self.current_actor.get().uri

    def spawn(
        self, action: Callable[..., Awaitable[None]], *args
    ) -> URIRef:
        uri = mint.fresh_uri(self.site)
        chan_send, chan_recv = trio.open_memory_channel(8)

        context = ActorContext(self.this(), uri, chan_send, chan_recv)
        self.actors[uri] = context
        with self.current_actor.bind(context):
            self.logger.info("spawning", actor=uri)

            async def task():
                try:
                    await action(*args)
                    self.logger.info("actor finished", actor=uri)

                    # If an exception happens here, what happens?
                    # If we don't catch it, the nursery will crash.
                    # Propagating is okay for now.

                except Exception as e:
                    logger.error("actor crashed", actor=uri, error=e)
                    raise

                finally:
                    del self.actors[uri]

            self.nursery.start_soon(task)
        return uri

    async def send(self, actor: URIRef, message: Graph):
        if actor not in self.actors:
            raise ValueError(f"Actor {actor} not found")
        await self.actors[actor].chan_send.send(message)

    @asynccontextmanager
    async def as_actor(self, actor: URIRef):
        with self.current_actor.bind(self.actors[actor]):
            try:
                yield
            except Exception as e:
                logger.error("error in actor", error=e, actor=actor)
                raise
            finally:
                del self.actors[actor]


current_actor_system = Parameter[ActorSystem]("current_actor_system")


def this() -> URIRef:
    return current_actor_system.get().this()


def spawn(action: Callable, *args):
    system = current_actor_system.get()
    return system.spawn(action, *args)


async def send(actor: URIRef, message: Optional[Graph] = None):
    system = current_actor_system.get()
    if message is None:
        message = vars.graph.get()
    logger.info("sending message", actor=actor, graph=message)
    return await system.send(actor, message)


async def receive() -> Graph:
    system = current_actor_system.get()
    return await system.current_actor.get().chan_recv.receive()


@asynccontextmanager
async def using_actor_system(
    site: str, logger: structlog.stdlib.BoundLogger
):
    try:
        async with trio.open_nursery() as nursery:
            system = ActorSystem(site, nursery, logger)
            with current_actor_system.bind(system):
                async with system.as_actor(system.this()):
                    yield system
                nursery.cancel_scope.cancel()
    except BaseException as e:
        logger.error("error using actor system", error=e)
        raise


@asynccontextmanager
async def as_temporary_actor() -> AsyncGenerator[URIRef, None]:
    system = current_actor_system.get()
    logger.info("as_temporary_actor", system=system)
    context = new_context(system.this())
    logger.info("as_temporary_actor", context=context)
    system.actors[context.uri] = context
    logger.info("as_temporary_actor", system=system)
    with current_actor_system.bind(system):
        async with system.as_actor(context.uri):
            yield context.uri


async def enter_actor_system(
    site: str, logger: structlog.stdlib.BoundLogger = structlog.get_logger()
):
    # make a channel to receive the actor system from the system task
    chan_send, chan_recv = trio.open_memory_channel(1)

    async def task():
        async with using_actor_system(site, logger) as system:
            await chan_send.send(system)
            while True:
                await trio.sleep(1)

    logger.info("starting actor system task")
    trio.lowlevel.spawn_system_task(task)
    logger.info("waiting for actor system task")
    system: ActorSystem = await chan_recv.receive()
    logger.info("actor system task ready", system=system)
    current_actor_system.set(system)
    context = new_context(system.this())
    system.actors[context.uri] = context
    system.current_actor.set(context)
    return system


class ServerActor[State]:
    def __init__(self, state: State):
        self.state = state

    async def __call__(self):
        try:
            while True:
                msg = await receive()
                logger.info("received message", graph=msg)
                response = await self.handle(msg)
                logger.info("sending response", graph=response)

                for reply_to in msg.objects(msg.identifier, NT.replyTo):
                    await send(URIRef(reply_to), response)
        except BaseException as e:
            logger.error("server actor crashed", error=e)
            raise

    async def handle(self, graph: Graph) -> Graph:
        raise NotImplementedError


async def call(actor: URIRef, payload: Optional[Graph] = None) -> Graph:
    if payload is None:
        payload = vars.graph.get()

    async with as_temporary_actor() as tmp:
        payload.add((payload.identifier, NT.replyTo, tmp))

        logger.info(
            "sending request",
            actor=actor,
            graph=payload,
        )
        await send(actor, payload)
        return await receive()


@contextmanager
def with_transient_graph(
    suffix: Optional[str] = None,
) -> Generator[URIRef, None, None]:
    site = current_actor_system.get().site
    if suffix is None:
        id = mint.fresh_uri(site)
    else:
        id = site[suffix]

    with vars.graph.bind(Graph(base=str(site), identifier=id)):
        yield id


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
    current_bubble.get().graph += graph


@contextmanager
def with_new_transaction(graph: Optional[Graph] = None):
    site = current_actor_system.get().site
    uri = mint.fresh_uri(site)
    g = Graph(base=str(site), identifier=uri)
    g.bind("nt", NT)
    g.bind("deepgram", DEEPGRAM)
    g.bind("site", site)
    if graph is not None:
        g += graph

    with vars.graph.bind(g):
        yield g
    logger.info("persisting transaction", graph=g)
    persist(g)


def town_app(
    base_url: str, bind: str, repo: BubbleRepo, root_actor: ServerActor
) -> FastAPI:
    logger = structlog.get_logger(__name__).bind(bind=bind)
    site = Namespace(base_url + "/")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("web app starting", site=site)
        app.mount(
            "/static",
            StaticFiles(
                directory=str(
                    pathlib.Path(__file__).parent.parent / "static"
                )
            ),
        )
        async with using_actor_system(str(site), logger) as system:
            app.state.actor_system = system

            root_actor_uri = spawn(root_actor)
            logger.info("spawned root actor", actor=root_actor_uri)

            create_affordance_button(root_actor_uri)

            app.state.root_actor = root_actor_uri

            yield
            logger.info("web app ending", app=app.state)

    def create_affordance_button(root_actor_uri):
        with with_new_transaction():
            new(
                URIRef("https://node.town/2024/deepgram/#Client"),
                {
                    NT.affordance: [
                        new(
                            NT.Button,
                            {
                                NT.label: Literal("Start", "en"),
                                NT.message: URIRef(
                                    "https://node.town/2024/deepgram/#Start"
                                ),
                                NT.target: root_actor_uri,
                            },
                            mint.fresh_uri(site),
                        )
                    ]
                },
                root_actor_uri,
            )

    app = FastAPI(lifespan=lifespan, debug=True)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allows all origins
        allow_credentials=True,
        allow_methods=["*"],  # Allows all methods
        allow_headers=["*"],  # Allows all headers
    )

    @app.exception_handler(Exception)
    async def all_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled exception", error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"error": "Internal Server Error", "details": str(exc)},
        )

    async def bind_document(request, call_next):
        with document():
            return await call_next(request)

    async def bind_actor_system(request, call_next):
        with current_actor_system.bind(app.state.actor_system):
            return await call_next(request)

    async def bind_bubble(request, call_next):
        with using_bubble(repo):
            repo.dataset.bind("site", site)
            return await call_next(request)

    app.middleware("http")(bind_document)
    app.middleware("http")(bind_actor_system)
    app.middleware("http")(bind_bubble)

    app.include_router(rdfa.router)

    @app.get("/favicon.ico")
    async def favicon():
        return Response(status_code=204)

    @app.get("/health")
    async def health_check():
        with with_transient_graph("health") as id:
            generate_health_status(id)
            return LinkedDataResponse()

    def generate_health_status(id):
        new(
            NT.HealthCheck,
            {
                NT.status: Literal("ok"),
                NT.actorSystem: this(),
            },
            subject=id,
        )

    @app.get("/.well-known/did.json")
    async def get_did_document():
        did_uri = generate_did_uri()

        with with_transient_graph(".well-known/did.json") as id:
            build_did_document(did_uri, id)

            return LinkedDataResponse(vocab=DID)

    def generate_did_uri():
        return URIRef(str(site).replace("https://", "did:web:").rstrip("/"))

    def build_did_document(did_uri, doc_uri):
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

    @app.post("/{id}")
    async def actor_post(id: str, body: dict = Body(...)):
        actor = site[id]
        with with_new_transaction() as g:
            body["@id"] = str(g.identifier)
            g.parse(data=json.dumps(body), format="json-ld")
            result = await call(actor, g)
            return LinkedDataResponse(result)

    @app.post("/{id}/message")
    async def actor_message(id: str, type: str = Form(...)):
        actor = site[id]
        with with_new_transaction() as g:
            record_message(type, actor, g)

            result = await call(actor, g)
            return LinkedDataResponse(result)

    def record_message(type, actor, g):
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

    async def handle_upload_stream(
        actor: URIRef, stream: AsyncGenerator[bytes, None]
    ):
        """Handle a stream of bytes for uploading, regardless of source."""
        async for chunk in stream:
            await send_chunk_to_actor(actor, chunk)

        # Send end marker
        with with_transient_graph() as id:
            new(NT.End, {}, id)
            await send(actor)

        # Return completion message
        with with_transient_graph() as id:
            new(NT.Done, {}, id)
            return vars.graph.get()

    @app.put("/{id}")
    async def actor_put(id: str, request: Request):
        actor = site[id]
        async with as_temporary_actor():

            async def request_stream():
                async for chunk in request.stream():
                    yield chunk

            result = await handle_upload_stream(actor, request_stream())
            return LinkedDataResponse(result)

    @contextmanager
    def install_context():
        """Install the actor system and bubble context for request handling."""
        with current_actor_system.bind(app.state.actor_system):
            with using_bubble(repo):
                yield

    @app.websocket("/{id}/upload")
    async def ws_upload(websocket: WebSocket, id: str):
        await websocket.accept()
        actor = site[id]
        logger.info("starting websocket upload", actor=actor)

        async def websocket_stream():
            while True:
                message = await websocket.receive_bytes()
                yield message

        with install_context():
            try:
                result = await handle_upload_stream(
                    actor, websocket_stream()
                )
                await websocket.send_json(
                    result.serialize(format="json-ld")
                )

            except Exception as e:
                logger.error("error in websocket upload", error=e)
                await websocket.close(code=1011, reason=str(e))
                raise
            finally:
                await websocket.close()

    @app.get("/{id}")
    async def actor_get(id: str):
        actor = current_actor_system.get().actors[site[id]]

        async def receive_messages_for_actor():
            while True:
                graph: Graph = await actor.chan_recv.receive()
                jsonld = graph.serialize(format="json-ld")
                yield f"event: message\ndata: {jsonld}\n\n"

        return StreamingResponse(
            receive_messages_for_actor(), media_type="text/event-stream"
        )

    @app.get("/")
    async def root():
        with base_html("Bubble"):
            rdf_resource(app.state.root_actor)
        return HypermediaResponse()

    async def send_chunk_to_actor(actor: URIRef, message: bytes) -> URIRef:
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

    return app


@contextmanager
def in_request_graph(g: Graph):
    with vars.graph.bind(g):
        yield g.identifier
