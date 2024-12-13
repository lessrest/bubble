from pathlib import Path
import re

from contextlib import asynccontextmanager

from structlog.stdlib import BoundLogger
import trio

from httpx import AsyncClient, ASGITransport
from pytest import fixture
from rdflib import Graph, URIRef, Dataset, Literal, Namespace
from asgi_lifespan import LifespanManager

from swash.mint import fresh_uri
from swash.prfx import NT, RDF
from swash.util import is_a, bubble, get_single_object
from bubble.logs import configure_logging
from bubble.repo import BubbleRepo, using_bubble_at
from bubble.town import (
    ServerActor,
    Site,
    call,
    send,
    this,
    spawn,
    receive,
    town_app,
)


@fixture
def logger():
    return configure_logging().bind(name="test")


@fixture
async def temp_repo(tmp_path: Path):
    """Create a temporary repository for testing"""
    async with using_bubble_at(tmp_path) as repo:
        yield repo


EX = Namespace("http://example.com/")


async def test_basic_actor_system(
    logger: BoundLogger, temp_repo: BubbleRepo
):
    async def ping_actor():
        msg = await receive()
        assert is_a(msg.identifier, EX.Ping, graph=msg)
        response_graph = Graph(identifier=fresh_uri(EX))
        response_graph.add((response_graph.identifier, RDF.type, EX.Pong))
        reply_to = get_single_object(msg.identifier, NT.replyTo, graph=msg)
        assert isinstance(reply_to, URIRef)
        await send(reply_to, response_graph)

    town = Site("http://example.com", "localhost:8000", repo=temp_repo)

    async with trio.open_nursery() as nursery:
        with town.install_context():
            ping_uri = await spawn(nursery, ping_actor)

            assert re.match(r"http://example.com/\w+", str(this()))
            assert re.match(r"http://example.com/\w+", str(ping_uri))

            ping_message = Graph()
            ping_message.add((ping_message.identifier, RDF.type, EX.Ping))
            ping_message.add((ping_message.identifier, NT.replyTo, this()))
            await send(ping_uri, ping_message)

            response = await receive()
            assert is_a(response.identifier, EX.Pong, graph=response)


class CounterActor(ServerActor[int]):
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


async def test_counter_actor(logger: BoundLogger, temp_repo: BubbleRepo):
    town = Site("http://example.com", "localhost:8000", repo=temp_repo)
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
async def client(temp_repo: BubbleRepo):
    app = town_app(
        "http://example.com",
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


async def test_health_check(client: AsyncClient, logger: BoundLogger):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.content
    id = URIRef(response.links["self"]["url"])

    graph = Graph()
    graph.parse(data, format="json-ld")
    logger.info("health check", data=data, base=graph.base)
    assert (None, NT.status, Literal("ok")) in graph
    # Verify we got a valid actor system URI back
    assert re.match(r"http://example.com/\w+", str(id))


async def test_actor_system_persistence(
    client: AsyncClient, logger: BoundLogger
):
    # Make two requests and verify we get the same actor system URI
    response1 = await client.get("/health")
    assert response1.status_code == 200
    id1 = URIRef(response1.links["self"]["url"])

    response2 = await client.get("/health")
    assert response2.status_code == 200
    id2 = URIRef(response2.links["self"]["url"])

    logger.info("response1", content=response1.content, id=id1)
    logger.info("response2", content=response2.content, id=id2)

    graph1 = Dataset()
    graph1.parse(response1.content, format="json-ld")
    graph2 = Dataset()
    graph2.parse(response2.content, format="json-ld")

    logger.info("graph1", graph=graph1, id=id1)
    logger.info("graph2", graph=graph2, id=id2)

    # The actor system URI should be the same across requests
    system1 = get_single_object(id1, NT.actorSystem, graph=graph1)
    system2 = get_single_object(id2, NT.actorSystem, graph=graph2)
    assert system1 == system2
