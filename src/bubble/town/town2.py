from typing import (
    Any,
    Callable,
    MutableMapping,
)
from contextlib import asynccontextmanager
from dataclasses import dataclass

import trio
import structlog

from rdflib import URIRef, Namespace

from swash import Parameter, mint

type Message = MutableMapping[str, Any]
type Scope = MutableMapping[str, Any]
type Receive = Callable[[], Any]
type Send = Callable[[Message], Any]
type App = Callable[[Scope, Receive, Send], Any]


@dataclass
class ActorContext:
    parent: URIRef
    uri: URIRef
    chan_send: trio.MemorySendChannel
    chan_recv: trio.MemoryReceiveChannel


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

    def spawn(self, action: Callable) -> URIRef:
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

    async def send(self, actor: URIRef, message: Message):
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


async def send(actor: URIRef, message: Message):
    system = current_actor_system.get()
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
                yield
