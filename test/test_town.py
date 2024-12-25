import re

from contextlib import asynccontextmanager

import trio

from trio import Path
from httpx import AsyncClient, ASGITransport
from pytest import fixture
from rdflib import Graph, URIRef, Literal, Namespace
from asgi_lifespan import LifespanManager
from structlog.stdlib import BoundLogger

from swash.mint import fresh_uri
from swash.prfx import NT, RDF
from swash.util import is_a, bubble, get_single_object
from bubble.logs import configure_logging
from bubble.mesh.otp import (
    ServerActor,
)
from bubble.repo.git import Git
from bubble.http.town import (
    Site,
    town_app,
)
from bubble.mesh.base import send, this, spawn, receive
from bubble.mesh.call import call
from bubble.repo.repo import Repository


@fixture
def logger():
    return configure_logging().bind(name="test")


@fixture
async def temp_repo(tmp_path: Path):
    """Create a temporary repository for testing"""
    repo = await Repository.create(Git(tmp_path), base_url_template=EX)
    yield repo


EX = Namespace("http://example.com/")


async def test_basic_actor_system(
    logger: BoundLogger, temp_repo: Repository
):
    async def ping_actor():
        msg = await receive()
        assert is_a(msg.identifier, EX.Ping, graph=msg)
        response_graph = Graph(identifier=fresh_uri(EX))
        response_graph.add((response_graph.identifier, RDF.type, EX.Pong))
        reply_to = get_single_object(msg.identifier, NT.replyTo, graph=msg)
        assert isinstance(reply_to, URIRef)
        await send(reply_to, response_graph)

    town = Site("http://example.com/", "localhost:8000", repo=temp_repo)

    async with trio.open_nursery() as nursery:
        with town.install_context():
            ping_uri = await spawn(nursery, ping_actor)

            assert re.match(
                r"http://example\.com/[A-Za-z0-9]+$", str(this())
            )
            assert re.match(
                r"http://example\.com/[A-Za-z0-9]+$", str(ping_uri)
            )

            ping_message = Graph()
            ping_message.add((ping_message.identifier, RDF.type, EX.Ping))
            ping_message.add((ping_message.identifier, NT.replyTo, this()))

            await send(ping_uri, ping_message)

            # Wait for response
            response = await receive()
            assert is_a(response.identifier, EX.Pong, graph=response)

            nursery.cancel_scope.cancel()


class CounterActor(ServerActor):
    def __init__(self, state: int):
        super().__init__()
        self.state = state

    async def handle(self, nursery: trio.Nursery, graph: Graph) -> Graph:
        if is_a(graph.identifier, EX.Inc, graph=graph):
            self.state += 1
            return bubble(EX.Inc, EX, {EX.value: Literal(self.state)})
        elif is_a(graph.identifier, EX.Get, graph=graph):
            return bubble(EX.Get, EX, {EX.value: Literal(self.state)})
        elif is_a(graph.identifier, EX.Stop, graph=graph):
            self.stop = True
            return Graph()
        else:
            raise ValueError(f"Unknown action: {graph.identifier}")


async def test_counter_actor(logger: BoundLogger, temp_repo: Repository):
    town = Site("http://example.com/", "localhost:8000", repo=temp_repo)
    with trio.fail_after(0.5):
        async with trio.open_nursery() as nursery:
            with town.install_context():
                counter = await spawn(nursery, CounterActor(0))

                # Test initial value
                x = await call(counter, bubble(EX.Get, EX))
                assert (x.identifier, EX.value, Literal(0)) in x

                # Test increment
                x = await call(counter, bubble(EX.Inc, EX))
                assert (x.identifier, EX.value, Literal(1)) in x

                # Test get after increment
                x = await call(counter, bubble(EX.Get, EX))
                assert (x.identifier, EX.value, Literal(1)) in x

                await call(counter, bubble(EX.Stop, EX))


@asynccontextmanager
@fixture
async def client(temp_repo: Repository):
    app = town_app(
        "http://example.com/",
        "localhost:8000",
        repo=temp_repo,
        root_actor=CounterActor(0),
    )
    async with LifespanManager(app) as manager:
        async with AsyncClient(
            base_url="http://example.com",
            transport=ASGITransport(app=manager.app),
        ) as client:
            yield client
