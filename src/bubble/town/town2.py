from base64 import b64encode
import json

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

import importhook

from pydantic import BaseModel
import trio
import structlog

from rdflib import XSD, Graph, URIRef, Literal, Namespace
from fastapi import Body, FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse, StreamingResponse
from trio_websocket import WebSocketConnection

from swash import Parameter, mint, vars
from swash.prfx import NT, DID
from swash.util import add, get_single_object, is_a, new, bubble
from bubble.repo import BubbleRepo, using_bubble
from bubble.talk import (
    DeepgramMessage,
    DeepgramParams,
    using_deepgram_live_session,
)


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

    def spawn(self, action: Callable[[], Awaitable[None]]) -> URIRef:
        uri = mint.fresh_uri(self.site)
        chan_send, chan_recv = trio.open_memory_channel(8)

        context = ActorContext(self.this(), uri, chan_send, chan_recv)
        self.actors[uri] = context
        with self.current_actor.bind(context):
            self.logger.info("spawning", actor=uri)

            async def task():
                try:
                    await action()

                    # If an exception happens here, what happens?
                    # If we don't catch it, the nursery will crash.
                    # Propagating is okay for now.

                finally:
                    self.logger.info("actor exited", actor=uri)
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
            finally:
                del self.actors[actor]


current_actor_system = Parameter[ActorSystem]("current_actor_system")


def this() -> URIRef:
    return current_actor_system.get().this()


def spawn(action: Callable):
    system = current_actor_system.get()
    return system.spawn(action)


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
    async with trio.open_nursery() as nursery:
        system = ActorSystem(site, nursery, logger)
        with current_actor_system.bind(system):
            async with system.as_actor(system.this()):
                yield system
            nursery.cancel_scope.cancel()


@asynccontextmanager
async def as_temporary_actor() -> AsyncGenerator[URIRef, None]:
    system = current_actor_system.get()
    context = new_context(system.this())
    system.actors[context.uri] = context
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
        while True:
            msg = await receive()
            logger.info("received message", graph=msg)
            response = await self.handle(msg)
            logger.info("sending response", graph=response)

            for reply_to in msg.objects(msg.identifier, NT.replyTo):
                await send(URIRef(reply_to), response)

    async def handle(self, graph: Graph) -> Graph:
        raise NotImplementedError


async def call(actor: URIRef, payload: Graph) -> Graph:
    async with as_temporary_actor():
        payload.add((payload.identifier, NT.replyTo, this()))

        logger.info(
            "sending request",
            actor=actor,
            graph=payload,
        )
        await send(actor, payload)
        return await receive()


@contextmanager
def in_fresh_graph(
    suffix: Optional[str] = None,
) -> Generator[URIRef, None, None]:
    site = current_actor_system.get().site
    if suffix is None:
        id = mint.fresh_uri(site)
    else:
        id = site[suffix]

    with vars.graph.bind(Graph(base=str(site), identifier=id)) as graph:
        yield id


class LinkedDataResponse(JSONResponse):
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
                # "did": str(DID),
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
        )


# FastAPI app


def town_app(
    base_url: str, bind: str, repo: BubbleRepo, root_actor: ServerActor
) -> FastAPI:
    logger = structlog.get_logger(__name__).bind(bind=bind)
    site = Namespace(base_url + "/")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("web app starting", site=site)
        async with using_actor_system(str(site), logger) as system:
            app.state.actor_system = system

            root_actor_uri = spawn(root_actor)
            logger.info("spawned root actor", actor=root_actor_uri)

            app.state.root_actor = root_actor_uri

            yield
            logger.info("web app ending", app=app.state)

    app = FastAPI(lifespan=lifespan)

    @app.middleware("http")
    async def catch_errors(request, call_next):
        try:
            return await call_next(request)
        except Exception as e:
            logger.error("error", error=e)
            return JSONResponse(status_code=500, content={"error": str(e)})

    @app.middleware("http")
    async def bind_actor_system(request, call_next):
        with current_actor_system.bind(app.state.actor_system):
            return await call_next(request)

    @app.middleware("http")
    async def bind_bubble(request, call_next):
        with using_bubble(repo):
            return await call_next(request)

    @app.get("/health")
    async def health_check():
        with in_fresh_graph("health") as id:
            new(
                NT.HealthCheck,
                {
                    NT.status: Literal("ok"),
                    NT.actorSystem: this(),
                },
                subject=id,
            )
            return LinkedDataResponse()

    @app.get("/.well-known/did.json")
    async def get_did_document():
        did_uri = generate_did_uri()

        with in_fresh_graph(".well-known/did.json") as id:
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

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()
        async with as_temporary_actor():
            while True:
                msg = await receive()
                await websocket.send_json(msg.serialize(format="json-ld"))

    @app.post("/{id}")
    async def actor_post(id: str, body: dict = Body(...)):
        if id == "root":
            actor = app.state.root_actor
        else:
            actor = site[id]

        g = Graph(base=str(site), identifier=mint.fresh_uri(site))
        body["@id"] = str(g.identifier)
        g.parse(data=json.dumps(body), format="json-ld")
        response = await call(actor, g)
        return LinkedDataResponse(response)

    @app.put("/{id}")
    async def actor_put(id: str, request: Request):
        if id == "root":
            actor = app.state.root_actor
        else:
            actor = site[id]

        async with as_temporary_actor() as temp_actor:
            logger.info("starting put", actor=actor, temp_actor=temp_actor)
            async for chunk in request.stream():
                logger.info("received chunk", chunk=len(chunk))
                with in_fresh_graph() as id:
                    new(
                        NT.Chunk,
                        {
                            NT.chunk: Literal(
                                b64encode(chunk), datatype=XSD.base64Binary
                            )
                        },
                        id,
                    )
                    await send(actor)
            with in_fresh_graph() as id:
                new(NT.End, {}, id)
                await send(actor)

            with in_fresh_graph() as id:
                new(NT.Done, {}, id)
                return LinkedDataResponse()

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

    return app


# Let's define a Deepgram client actor...

Deepgram = Namespace("https://node.town/2024/deepgram/#")


@contextmanager
def in_request_graph(g: Graph):
    with vars.graph.bind(g):
        yield g.identifier


class DeepgramClientActor(ServerActor[str]):
    async def handle(self, graph: Graph) -> Graph:
        with in_request_graph(graph) as msg:
            if is_a(msg, Deepgram.Start):

                async def deepgram_results_actor():
                    while True:
                        await trio.sleep(1)

                results = spawn(deepgram_results_actor)

                async def deepgram_client_actor():
                    # Wait for first chunk before starting session
                    with in_request_graph(await receive()) as msg:
                        logger.info("received first message", msg=msg)
                        if not is_a(msg, NT.Chunk):
                            logger.error("expected chunk message")
                            return

                        first_chunk = get_single_object(
                            msg, NT.chunk
                        ).toPython()

                        async with using_deepgram_live_session(
                            DeepgramParams()
                        ) as client:

                            async def receive_results():
                                while True:
                                    result = await client.get_message()
                                    message = (
                                        DeepgramMessage.model_validate_json(
                                            result
                                        )
                                    )
                                    if message.channel.alternatives[
                                        0
                                    ].transcript:
                                        logger.info(
                                            "Deepgram message",
                                            message=message,
                                        )
                                        with in_fresh_graph() as id:
                                            new(
                                                Deepgram.Result,
                                                {
                                                    Deepgram.transcript: message.channel.alternatives[
                                                        0
                                                    ].transcript
                                                },
                                                id,
                                            )
                                            await send(results)

                            spawn(receive_results)

                            # Send the first chunk we received
                            await client.send_message(first_chunk)

                            # Handle remaining messages
                            while True:
                                with in_request_graph(
                                    await receive()
                                ) as msg:
                                    if is_a(msg, NT.Chunk):
                                        chunk = get_single_object(
                                            msg, NT.chunk
                                        )
                                        bytes = chunk.toPython()
                                        await client.send_message(bytes)

                session = spawn(deepgram_client_actor)
                add(msg, {NT.spawned: session})
                add(msg, {NT.spawned: results})
                new(Deepgram.Session, {}, session)
                new(Deepgram.Results, {}, results)

            return graph
