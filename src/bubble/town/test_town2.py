from contextlib import asynccontextmanager
import re
from typing import Sequence

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
import structlog

from pytest import fixture
from rdflib import Dataset, Graph, Literal, URIRef, Namespace
from pydantic import BaseModel
from fastapi.testclient import TestClient

from swash.mint import fresh_uri
from swash.prfx import NT, RDF
from swash.util import O, P, S, get_single_object, is_a, get_single_subject
from swash.util import bubble
import trio
from bubble.logs import configure_logging
from bubble.repo import BubbleRepo, using_bubble_at
from bubble.town.town2 import (
    ServerActor,
    call,
    send,
    this,
    spawn,
    receive,
    using_actor_system,
    town_app,
)


@fixture
def logger():
    return configure_logging().bind(name="test")


EX = Namespace("http://example.com/")


async def test_basic_actor_system(logger):
    async with using_actor_system("http://example.com/", logger):

        async def ping_actor():
            msg = await receive()
            assert is_a(msg.identifier, EX.Ping, graph=msg)
            response_graph = Graph(identifier=fresh_uri(EX))
            response_graph.add(
                (response_graph.identifier, RDF.type, EX.Pong)
            )
            reply_to = get_single_object(
                msg.identifier, NT.replyTo, graph=msg
            )
            assert isinstance(reply_to, URIRef)
            await send(reply_to, response_graph)

        ping_uri = spawn(ping_actor)

        assert re.match(r"http://example.com/\w+", str(this()))
        assert re.match(r"http://example.com/\w+", str(ping_uri))

        ping_message = Graph()
        ping_message.add((ping_message.identifier, RDF.type, EX.Ping))
        ping_message.add((ping_message.identifier, NT.replyTo, this()))
        await send(ping_uri, ping_message)

        response = await receive()
        assert is_a(response.identifier, EX.Pong, graph=response)


class CounterActor(ServerActor[int]):
    async def handle(self, request: Graph) -> Graph:
        if is_a(request.identifier, EX.Inc, graph=request):
            self.state += 1
            return bubble(EX.Inc, EX, {EX.value: Literal(self.state)})
        elif is_a(request.identifier, EX.Get, graph=request):
            return bubble(EX.Get, EX, {EX.value: Literal(self.state)})
        else:
            raise ValueError(f"Unknown action: {request.identifier}")


async def test_counter_actor(logger):
    with trio.fail_after(0.5):
        async with using_actor_system("http://example.com/", logger):
            counter = spawn(CounterActor(0))

            # Test initial value
            x = await call(counter, bubble(EX.Get, EX))
            assert (x.identifier, EX.value, Literal(0)) in x

            # Test increment
            x = await call(counter, bubble(EX.Inc, EX))
            assert (x.identifier, EX.value, Literal(1)) in x

            # Test get after increment
            x = await call(counter, bubble(EX.Get, EX))
            assert (x.identifier, EX.value, Literal(1)) in x


@fixture
async def temp_repo(tmp_path):
    """Create a temporary repository for testing"""
    async with using_bubble_at(tmp_path) as repo:
        yield repo


@asynccontextmanager
@fixture
async def client(temp_repo):
    app = town_app("http://example.com", "localhost:8000", repo=temp_repo)
    async with LifespanManager(app) as manager:
        async with AsyncClient(
            base_url="http://example.com",
            transport=ASGITransport(app=manager.app),
        ) as client:
            yield client


async def test_health_check(client: AsyncClient, logger):
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


async def test_actor_system_persistence(client, logger):
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
