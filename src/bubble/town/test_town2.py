import re

import structlog

from pytest import fixture
from rdflib import Graph, Literal, URIRef, Namespace
from pydantic import BaseModel

from swash.mint import fresh_uri
from swash.prfx import NT, RDF
from swash.util import get_single_object, is_a, get_single_subject
import trio
from bubble.logs import configure_logging
from bubble.town.town2 import (
    ServerActor,
    call,
    send,
    this,
    spawn,
    receive,
    using_actor_system,
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
            response_graph = Graph(identifier=fresh_uri(EX))
            response_graph.add(
                (response_graph.identifier, RDF.type, EX.Inc)
            )
            response_graph.add(
                (response_graph.identifier, EX.value, Literal(self.state))
            )
            return response_graph
        elif is_a(request.identifier, EX.Get, graph=request):
            response_graph = Graph(identifier=fresh_uri(EX))
            response_graph.add(
                (response_graph.identifier, RDF.type, EX.Get)
            )
            response_graph.add(
                (response_graph.identifier, EX.value, Literal(self.state))
            )
            return response_graph
        else:
            raise ValueError(f"Unknown action: {request.identifier}")


async def test_counter_actor(logger):
    with trio.fail_after(0.5):
        async with using_actor_system("http://example.com/", logger):
            counter = spawn(CounterActor(0))

            # Test initial value
            get_graph = Graph(identifier=fresh_uri(EX))
            get_graph.add((get_graph.identifier, RDF.type, EX.Get))
            x = await call(counter, get_graph)
            assert (x.identifier, EX.value, Literal(0)) in x

            # Test increment
            inc_graph = Graph(identifier=fresh_uri(EX))
            inc_graph.add((inc_graph.identifier, RDF.type, EX.Inc))
            x = await call(counter, inc_graph)
            assert (x.identifier, EX.value, Literal(1)) in x

            # Test get after increment
            get_graph = Graph(identifier=fresh_uri(EX))
            get_graph.add((get_graph.identifier, RDF.type, EX.Get))
            x = await call(counter, get_graph)
            assert (x.identifier, EX.value, Literal(1)) in x
