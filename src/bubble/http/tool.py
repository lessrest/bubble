"""Digital Craftsmanship: The Art of Message Handling

In traditional crafts, a master artisan's workshop is organized around
their tools - each with its place, each with its purpose. In our
digital workshop, we organize around message handlers and actors,
each precisely tuned to handle specific types of interactions.

This module implements a sophisticated message handling system where:

- Actors are our master craftsmen
- Messages are their raw materials
- Handlers are their specialized tools
- Graphs are their workbenches

Historical note: The actor model dates back to 1973, but like a
well-maintained craftsman's tool, it has only grown more valuable
with time. Here we blend it with modern Python's type system and
async capabilities.
"""

from typing import (
    Dict,
    List,
    Self,
    Callable,
    ClassVar,
    Optional,
    Protocol,
    Awaitable,
    AsyncGenerator,
)
from contextlib import asynccontextmanager
from dataclasses import dataclass

import structlog

from trio import Nursery
from rdflib import PROV, Graph, URIRef, Literal

from swash.prfx import NT
from swash.util import add, new, is_a
from bubble.mesh.otp import (
    ServerActor,
)
from bubble.mesh.base import (
    this,
    spawn,
    persist,
    txgraph,
)
from bubble.repo.repo import context, timestamp

logger = structlog.get_logger()


class AsyncReadable(Protocol):
    """Protocol for objects that can be read asynchronously."""

    async def aread(self) -> bytes: ...


@dataclass
class DispatchContext:
    """Context for message dispatch handling.

    Like a craftsman's workbench, this context provides everything
    needed to handle a message - the nursery for spawning helpers,
    the graph for recording work, and the request ID for tracking
    our creation.
    """

    nursery: Nursery
    buffer: Graph
    request_id: URIRef


# ------------------------------------
# Helper Functions
# ------------------------------------


@asynccontextmanager
async def persist_graph_changes(graph_id: URIRef):
    """Context manager to bind to a graph, apply updates, and persist changes.

    Like a master craftsman signing their work, this ensures our
    changes are properly recorded and preserved. It's the digital
    equivalent of applying a final protective finish to a piece
    of fine woodwork.
    """
    with context.bind_graph(graph_id) as sheet:
        try:
            yield sheet
            await persist(sheet)
        finally:
            pass  # Any cleanup if needed


@asynccontextmanager
async def new_persistent_graph() -> AsyncGenerator[URIRef, None]:
    async with txgraph() as graph:
        assert isinstance(graph.identifier, URIRef)
        yield graph.identifier


def create_button(
    label: str,
    icon: Optional[str],
    message_type: URIRef,
    target: Optional[URIRef] = None,
) -> URIRef:
    """Create a button affordance with a given label and message type.

    Like crafting a fine tool handle, this shapes raw materials
    (label, icon, message type) into a polished interface element
    that fits perfectly in the user's hand.
    """
    return new(
        NT.Button,
        {
            NT.label: Literal(label, "en"),
            NT.icon: icon,
            NT.message: message_type,
            NT.target: target or this(),
        },
    )


def create_prompt(
    label: str,
    placeholder: str,
    message_type: URIRef,
    target: Optional[URIRef] = None,
) -> URIRef:
    """Create a prompt affordance for text, image, or video generation."""
    return new(
        NT.Prompt,
        {
            NT.label: Literal(label, "en"),
            NT.placeholder: Literal(placeholder, "en"),
            NT.message: message_type,
            NT.target: target or this(),
        },
    )


async def add_affordance_to_sheet(graph_id: URIRef, affordance: URIRef):
    """Add an affordance to the sheet and persist."""
    async with persist_graph_changes(graph_id):
        add(graph_id, {NT.affordance: affordance})


async def spawn_actor(
    nursery, actor_class, *args, name: Optional[str] = None
) -> URIRef:
    """Spawn a new actor and return the actor's URIRef."""
    actor = actor_class(*args)
    actor_uri = await spawn(nursery, actor, name=name)
    return actor_uri


async def store_generated_assets(
    graph_id: URIRef,
    assets: List[
        tuple[AsyncReadable, str]
    ],  # List of (readable, mimetype) tuples
):
    """Store binary assets in the repository and link them to the graph."""
    async with persist_graph_changes(graph_id):
        distributions = []
        for readable, mime_type in assets:
            data = await readable.aread()
            distribution = await context.repo.get().save_blob(
                data, mime_type
            )
            add(
                distribution,
                {
                    PROV.wasGeneratedBy: this(),
                    PROV.generatedAtTime: timestamp(),
                    NT.mimeType: Literal(mime_type),
                },
            )
            distributions.append(distribution)

        if len(distributions) > 1:
            thing = new(
                PROV.Collection, {PROV.hadMember: set(distributions)}
            )
        elif len(distributions) == 1:
            thing = distributions[0]
        else:
            raise ValueError("No distributions to store")

        add(graph_id, {PROV.hadMember: thing})

        return thing


# ------------------------------------
# Dispatching Actor
# ------------------------------------


def handler[T](msg_type: URIRef) -> Callable[[T], T]:
    """A decorator to register a handler method for a given message type.

    Like a master craftsman's stamp that marks each tool for its
    specific purpose, this decorator marks methods to handle
    specific types of messages. It's how we maintain order in
    our digital workshop.
    """

    def decorator(fn: T) -> T:
        setattr(fn, "_handler_msg_type", msg_type)
        return fn

    return decorator


class DispatchingActor(ServerActor):
    """A base actor that provides structured message handling via decorators.

    Like a master craftsman who can handle many different types of
    work, this actor knows how to process various message types
    through its registered handlers. It's the foundation of our
    digital workshop, where each message is carefully routed to
    the right specialist.

    This class is intended to be subclassed by actors that need to handle
    messages and persist changes to their own identity graphs, which we call
    sheets because they are mutable containers for content.
    """

    _message_handlers: ClassVar[
        Dict[URIRef, Callable[[Self, DispatchContext], Awaitable[Graph]]]
    ] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        # Collect all handler methods from this class.
        handlers: Dict[
            URIRef, Callable[[Self, DispatchContext], Awaitable[Graph]]
        ] = {}

        for name, method in cls.__dict__.items():
            msg_type = getattr(method, "_handler_msg_type", None)
            if msg_type is not None and callable(method):
                handlers[msg_type] = method

        # Merge this class's handlers with any inherited ones
        # so that derived classes don't lose their parent class handlers.
        cls._message_handlers = {
            **getattr(cls, "_message_handlers", {}),
            **handlers,
        }

    async def setup(self, actor_uri: URIRef):
        pass

    async def handle(self, nursery: Nursery, graph: Graph) -> Graph:
        request_id = graph.identifier
        if not isinstance(request_id, URIRef):
            raise ValueError(
                f"Expected URIRef identifier, got {type(request_id)}"
            )

        ctx = DispatchContext(
            nursery=nursery,
            buffer=graph,
            request_id=request_id,
        )

        for msg_type, handler_method in self._message_handlers.items():
            if is_a(request_id, msg_type, graph):
                return await handler_method(self, ctx)

        raise ValueError(f"Unexpected message type: {request_id}")

    def current_graph(self) -> Graph:
        """Convenience to return the current context graph."""
        return context.buffer.get()
