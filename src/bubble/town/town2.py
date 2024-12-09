import json

from typing import (
    Any,
    Dict,
    Callable,
    Optional,
    Awaitable,
    AsyncGenerator,
    MutableMapping,
)
from datetime import UTC, datetime
from contextlib import asynccontextmanager
from dataclasses import dataclass

import pyld
import trio
import structlog

from rdflib import XSD, Graph, URIRef, Literal, Namespace
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from swash import Parameter, mint, vars
from swash.prfx import NT, DID
from swash.util import new, bubble
from bubble.repo import BubbleRepo, using_bubble

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

            async def task():
                try:
                    await action()

                    # If an exception happens here, what happens?
                    # If we don't catch it, the nursery will crash.
                    # Propagating is okay for now.

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
            finally:
                del self.actors[actor]


current_actor_system = Parameter[ActorSystem]("current_actor_system")


def this() -> URIRef:
    return current_actor_system.get().this()


def spawn(action: Callable):
    system = current_actor_system.get()
    return system.spawn(action)


async def send(actor: URIRef, message: Graph):
    system = current_actor_system.get()
    logger.info("sending message", actor=actor, graph=message)
    return await system.send(actor, message)


async def receive():
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

    async def handle(self, request: Graph) -> Graph:
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


class LinkedDataResponse(JSONResponse):
    def __init__(
        self,
        graph: Graph,
        *,
        vocab: Optional[Namespace] = None,
        context: Optional[Dict] = None,
        status_code: int = 200,
        headers: Optional[Dict[str, str]] = None,
    ):
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


def town_app(base_url: str, bind: str, repo: BubbleRepo) -> FastAPI:
    logger = structlog.get_logger(__name__).bind(bind=bind)
    site = Namespace(base_url + "/")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("web app starting", app=app.state)
        async with using_actor_system(base_url, logger) as system:
            app.state.actor_system = system

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
        doc_uri = site["health"]
        with vars.graph.bind(
            Graph(identifier=doc_uri, base=str(site))
        ) as graph:
            new(
                NT.HealthCheck,
                {
                    NT.status: Literal("ok"),
                    NT.actorSystem: this(),
                },
                subject=doc_uri,
            )
            return LinkedDataResponse(graph)

    @app.get("/.well-known/did.json")
    async def get_did_document():
        did_uri = URIRef(
            str(site).replace("https://", "did:web:").rstrip("/")
        )
        doc_uri = site[".well-known/did.json"]

        with vars.graph.bind(Graph(base=str(site))) as graph:
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

        return LinkedDataResponse(graph, vocab=DID)

    return app
