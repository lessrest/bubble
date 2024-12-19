"""Open Telecom Platform (OTP) inspired patterns for our actor system.

In the beginning, there was Erlang OTP, and it was good. So good that
we're shamelessly inspired by it here. But this isn't your grandfather's
OTP - this is OTP for the semantic web age, where every actor has a URI
and every message is a graph.

Historical note: The name OTP comes from Erlang's telecom origins at Ericsson.
We keep the name as a tribute, even though our actors are more likely to be
processing RDF graphs than routing phone calls. Progress?
"""

from typing import (
    Any,
    Dict,
    TypeVar,
    Callable,
)
from datetime import UTC, datetime

import trio
import tenacity
import structlog

from rdflib import (
    RDF,
    XSD,
    Graph,
    URIRef,
    Literal,
)

from swash.prfx import NT
from swash.util import P, add, new
from bubble.mesh.base import (
    send,
    this,
    spawn,
    receive,
    txgraph,
    create_graph,
)

logger = structlog.get_logger()

State = TypeVar("State")


class ServerActor[State]:
    """A long-running actor that processes messages, inspired by gen_server.

    Like a Buddhist monk maintaining their meditation through distractions,
    these actors maintain their state through a stream of messages.

    The State type parameter represents the actor's inner peace - or at
    least its internal state. Choose it wisely.
    """

    def __init__(self, state: State):
        """Initialize the actor with its initial state.

        Args:
            state: The initial state. Like the first thought of the day,
                  it sets the tone for what follows.
        """
        self.state = state
        self.name = self.__class__.__name__
        self.stop = False

    async def __call__(self):
        """Main actor message processing loop with error handling.

        This is where the magic happens. Like a cosmic dance of message
        passing, each actor gracefully moves through its lifecycle,
        processing messages until it's time to exit stage left.

        Warning: The try-except block here has seen things you people
        wouldn't believe. Attack ships on fire off the shoulder of
        Orion? Try debugging a distributed actor system.
        """
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
        """Initialize the actor before it begins its performance.

        Override this method to set up your actor's world before the
        curtain rises. The default implementation does nothing, like
        a zen master sitting quietly.
        """
        pass

    async def handle(self, nursery: trio.Nursery, graph: Graph) -> Graph:
        """Handle an incoming message, producing a response.

        This is the method you must override. It's your actor's raison d'être,
        its purpose in the grand cosmic dance of computation.

        Args:
            nursery: A trio nursery for spawning child tasks. Use wisely.
            graph: The incoming message as an RDF graph. Truth comes in triples.

        Returns:
            The response graph. Make it meaningful.

        Raises:
            NotImplementedError: Because abstract methods need love too.
        """
        raise NotImplementedError


class SimpleSupervisor:
    """A simple supervisor that manages named actors.

    This is our humble homage to OTP supervisors. While not as battle-tested
    as its Erlang ancestors, it tries its best to keep its children alive
    and healthy in this cruel, exception-filled world.

    Note: The commented-out retry logic is a testament to the eternal
    struggle between perfect fault tolerance and actually shipping code.
    """

    def __init__(self, actors: dict[str, Callable]):
        """Initialize with a dictionary mapping names to actor constructors.

        Args:
            actors: Dictionary mapping actor names to their constructor callables.
                   Choose names that spark joy.
        """
        self.actors = actors

    async def __call__(self):
        """Start supervising our merry band of actors.

        Like a kindergarten teacher with supernatural powers, we create
        our actors and watch over them as they play in their async sandbox.
        """
        async with txgraph():
            new(NT.Supervisor, {}, this())

        def retry_sleep(retry_state: tenacity.RetryCallState) -> Any:
            return logger.warning(
                "supervised actor tree crashed; retrying after exponential backoff",
                retrying=retry_state,
            )

        async with trio.open_nursery() as nursery:
            for name, actor in self.actors.items():
                # The commented-out retry logic below is like a good intention -
                # paving the way to production hell since forever.
                #
                # retry = tenacity.AsyncRetrying(
                #     wait=tenacity.wait_exponential(multiplier=1, max=60),
                #     retry=tenacity.retry_if_exception_type(
                #         (trio.Cancelled, BaseExceptionGroup)
                #     ),
                #     before_sleep=retry_sleep,
                # )
                # async for attempt in retry:
                #    with attempt:
                logger.info(
                    "starting supervised actor", actor=actor, name=name
                )
                child = await spawn(nursery, actor, name=name)
                add(this(), {NT.supervises: child})


def record_message(
    type: str,
    actor: URIRef,
    g: Graph,
    properties: Dict[P, Any] = {},
):
    """Record a message in the graph."""
    assert isinstance(g.identifier, URIRef)
    new(
        URIRef(type),
        {
            NT.created: Literal(
                datetime.now(UTC).isoformat(), datatype=XSD.dateTime
            ),
            NT.target: actor,
            **properties,
        },
        g.identifier,
    )


class UptimeActor(ServerActor[datetime]):
    """Actor that tracks and reports uptime since its creation.

    The digital equivalent of a monastery's timekeeper, marking the
    passage of time since its awakening. A reminder that in distributed
    systems, even time itself is relative.
    """

    async def init(self):
        """Mark our birth time in the eternal now."""
        self.state = datetime.now(UTC)
        async with txgraph():
            new(NT.UptimeActor, {}, this())

    async def handle(self, nursery, graph: Graph) -> Graph:
        """Calculate and report how long we've been contemplating existence.

        Returns a graph containing our uptime - a measurement of our
        persistence in this ephemeral digital realm.
        """
        request_id = graph.identifier
        uptime = datetime.now(UTC) - self.state

        g = create_graph()
        g.add((g.identifier, RDF.type, NT.UptimeResponse))
        g.add((g.identifier, NT.uptime, Literal(str(uptime))))
        g.add((g.identifier, NT.isResponseTo, request_id))

        # If there's a replyTo field, add it to response
        for reply_to in graph.objects(request_id, NT.replyTo):
            g.add((g.identifier, NT.replyTo, reply_to))

        return g
