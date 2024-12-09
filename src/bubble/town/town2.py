from typing import (
    Any,
    AsyncGenerator,
    Awaitable,
    Callable,
    Generator,
    MutableMapping,
    Optional,
    Type,
)
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import Depends, FastAPI, Response
from pydantic import BaseModel, JsonValue
from swash.prfx import NT
from swash.util import bubble
import trio
import structlog
from fastapi.responses import JSONResponse

from rdflib import Graph, Literal, URIRef, Namespace

from swash import Parameter, mint

type Message = MutableMapping[str, Any]
type Scope = MutableMapping[str, Any]
type Receive = Callable[[], Any]
type Send = Callable[[Message], Any]
type App = Callable[[Scope, Receive, Send], Any]

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


# FastAPI app


def new_town(base_url: str, bind: str) -> FastAPI:
    logger = structlog.get_logger(__name__).bind(bind=bind)
    site = Namespace(base_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("starting lifespan", app=app.state)
        async with using_actor_system(base_url, logger) as system:
            logger.info(
                "setting actor system", app=app.state, actor_system=system
            )
            app.state.actor_system = system

            yield

    app = FastAPI(lifespan=lifespan)

    async def bind_actor_system(request, call_next):
        logger.info(
            "binding actor system",
            app=app.state,
            actor_system=app.state.actor_system,
        )
        with current_actor_system.bind(app.state.actor_system):
            return await call_next(request)

    app.middleware("http")(bind_actor_system)

    @app.get("/health")
    async def health_check():
        graph = bubble(
            NT.HealthCheck,
            site,
            {
                NT.status: Literal("ok"),
                NT.actorSystem: this(),
            },
        )
        return Response(
            graph.serialize(format="trig"),
            media_type="text/trig",
            headers={
                "Link": f'<{str(graph.identifier)}>; rel="self"',
            },
        )

    return app
