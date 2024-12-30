"""The foundation of our actor system, where digital souls come to life.

As Alan Kay once said, "The best way to predict the future is to invent it."
This module invents a future where every computation is an actor, every message
a promise, and every failure a chance for redemption through supervision.

Historical note: The actor model was first described by Carl Hewitt in 1973.
Sadly, it took the industry several decades of pain with shared-state concurrency
before realizing he was right all along.
"""

from typing import (
    Set,
    Dict,
    Callable,
    Optional,
    Protocol,
    Awaitable,
    Generator,
    MutableMapping,
)
from datetime import UTC, datetime
from contextlib import contextmanager, asynccontextmanager
from collections import defaultdict
from dataclasses import dataclass

import trio
import structlog

from rdflib import XSD, PROV, RDFS, Graph, URIRef, Literal, Namespace
from typing_extensions import runtime_checkable
from cryptography.hazmat.primitives.asymmetric import ed25519

from swash import Parameter, here, mint
from swash.prfx import NT, DID, DEEPGRAM
from swash.util import add, new, blank
from bubble.keys import (
    generate_keypair,
    get_public_key_hex,
    get_public_key_bytes,
    create_identity_graph,
    generate_identity_uri,
)
from bubble.repo.repo import context

logger = structlog.get_logger()


@runtime_checkable
class SetupableActor(Protocol):
    """An actor that requires initialization before its performance begins.

    Like a method actor preparing for a role, these actors need time to get
    into character before the main show starts.
    """

    async def setup(self, actor_uri: URIRef): ...


def fresh_uri(site: Optional[Namespace] = None) -> URIRef:
    """Generate a fresh URI for a new entity in our digital theater.

    As Shakespeare wrote, "What's in a name? That which we call a rose
    By any other name would smell as sweet." But in our case, names
    really do matter - they're how our actors find each other.
    """
    if site is None:
        site = vat.get().site
    return mint.fresh_uri(site)


@dataclass
class ActorContext:
    """The existential context of an actor's being.

    Every actor exists within a context - its boss (supervisor), its own
    identity (addr), and its current incarnation (proc). Like humans,
    actors are defined both by their relationships and their individuality.

    The 'trap' flag determines whether errors propagate upward - a feature
    that has caused more philosophical debates than any boolean should.
    """

    boss: URIRef  # The entity responsible for our existence
    addr: URIRef  # Our eternal identity
    proc: URIRef  # Our current incarnation
    send: trio.MemorySendChannel  # Our voice to the world
    recv: trio.MemoryReceiveChannel  # Our ear to the world
    name: str = "anonymous"  # For those who prefer not to be just a URI
    trap: bool = False  # To trap or not to trap, that is the exception


def root_context(site: Namespace, name: str = "root") -> ActorContext:
    """Create the primordial context, the first mover, the unmoved mover.

    Every actor system needs its root, its alpha and omega. This function
    creates that blessed context from which all other contexts spring.
    """
    uri = fresh_uri(site)
    chan_send, chan_recv = trio.open_memory_channel(
        8
    )  # 8: a number chosen by fair dice roll
    return ActorContext(uri, uri, uri, chan_send, chan_recv, name=name)


def new_context(parent: URIRef, name: str = "unnamed") -> ActorContext:
    """Birth a new context from a parent, in the eternal cycle of actor creation.

    Note: We use a channel buffer size of 8 messages. Why 8? Why not? The
    universe seems to favor powers of 2, who are we to argue?
    """
    chan_send, chan_recv = trio.open_memory_channel(8)
    return ActorContext(
        parent, fresh_uri(), fresh_uri(), chan_send, chan_recv, name=name
    )


@contextmanager
def with_transient_graph(
    suffix: Optional[str] = None,
) -> Generator[URIRef, None, None]:
    """Create a temporary graph that will fade like tears in rain.

    As ephemeral as a summer breeze, these graphs exist only to serve
    a momentary purpose before returning to the void. They are the
    digital equivalent of zen sand mandalas.
    """
    g = create_graph(suffix)
    with here.graph.bind(g):
        assert isinstance(g.identifier, URIRef)
        yield g.identifier


class Vat:
    site: Namespace
    curr: Parameter[ActorContext]
    deck: MutableMapping[URIRef, ActorContext]
    yell: structlog.stdlib.BoundLogger
    private_key: ed25519.Ed25519PrivateKey
    public_key: ed25519.Ed25519PublicKey
    identity_uri: URIRef
    base_url: str

    def __init__(
        self,
        site: str,
        yell: structlog.stdlib.BoundLogger,
    ):
        self.site = Namespace(site)
        self.base_url = str(self.site[""])
        self.yell = yell.bind(site=site)
        self.nats = None

        # Generate Ed25519 keypair
        self.private_key, self.public_key = generate_keypair()
        self.identity_uri = generate_identity_uri(self.public_key)
        self.yell.info("generated Ed25519 keypair")

        root = root_context(self.site)
        self.curr = Parameter("current_actor", root)
        self.deck = {root.addr: root}

    async def setup_nats(self, nats_url: str):
        """Set up NATS for mesh networking."""
        from bubble.mesh.nats import TrioNatsClient

        self.nats = TrioNatsClient(nats_url)
        await self.nats.connect()

        async def handle_remote_actor_message(
            actor_uri: str, message: bytes
        ):
            """Handle messages received from other nodes in the cluster."""
            actor = URIRef(actor_uri)
            if actor not in self.deck:
                # Message is not for an actor on this node
                return

            # Parse the message into a graph
            g = Graph()
            g.parse(data=message.decode(), format="trig")

            # Send to local actor
            await self.deck[actor].send.send(g)

        await self.nats.subscribe_to_actor_messages(
            handle_remote_actor_message
        )

    async def send(self, actor: URIRef, message: Optional[Graph] = None):
        if message is None:
            message = here.graph.get()

        if actor in self.deck:
            # Local actor
            await self.deck[actor].send.send(message)
        elif self.nats and self.nats.connected:
            # Try broadcasting via NATS if actor not found locally
            message_data = message.serialize(format="trig").encode()
            await self.nats.broadcast_actor_message(
                str(actor), message_data
            )
            self.yell.info("broadcasted message via NATS", actor=actor)
        else:
            raise ValueError(f"No route found for actor {actor}")

    def get_base_url(self) -> str:
        return self.base_url

    def get_public_key_bytes(self) -> bytes:
        """Get the raw bytes of the public key."""
        return get_public_key_bytes(self.public_key)

    def get_public_key_hex(self) -> str:
        """Get the hex representation of the public key."""
        return get_public_key_hex(self.public_key)

    def create_identity_graph(self):
        """Create a graph representing this town's cryptographic identity."""
        create_identity_graph(self.public_key, self.identity_uri)

    def sign_data(self, data: bytes) -> bytes:
        """Sign data using the town's Ed25519 private key."""
        return self.private_key.sign(data)

    def verify_signature(self, data: bytes, signature: bytes) -> bool:
        """Verify a signature using the town's Ed25519 public key."""
        try:
            self.public_key.verify(signature, data)
            return True
        except Exception:
            return False

    def this(self) -> URIRef:
        return self.curr.get().addr

    async def spawn(
        self,
        crib: trio.Nursery,
        code: Callable[..., Awaitable[None]],
        *args,
        name: Optional[str] = None,
    ) -> URIRef:
        if name is None:
            if hasattr(code, "__name__"):
                name = code.__name__
            else:
                name = code.__class__.__name__

        parent_ctx = self.curr.get()
        context = new_context(parent_ctx.addr, name=name)
        parent = parent_ctx.addr
        parent_proc = parent_ctx.proc
        actor = context.addr
        actor_proc = context.proc
        self.deck[context.addr] = context

        self.yell.info(
            "spawning",
            actor=actor,
            actor_name=name,
            parent=parent,
        )

        # new(
        #     OWL.Class,
        #     {
        #         RDFS.label: Literal("actor process", lang="en"),
        #         RDFS.subClassOf: PROV.Activity,
        #     },
        #     subject=NT.ActorProcess,
        # )
        # new(
        #     OWL.Class,
        #     {
        #         RDFS.label: Literal("actor", lang="en"),
        #         RDFS.subClassOf: [PROV.Entity, PROV.SoftwareAgent],
        #     },
        #     subject=NT.Actor,
        # )

        now = Literal(datetime.now(UTC), datatype=XSD.dateTime)

        new(
            NT.ActorProcess,
            {
                PROV.startedAtTime: now,
                PROV.wasAssociatedWith: parent_proc,
            },
            actor_proc,
        )

        add(
            actor,
            {
                RDFS.label: Literal(name, lang="en"),
                PROV.wasGeneratedBy: parent_proc,
                PROV.generatedAtTime: now,
                PROV.wasAssociatedWith: actor_proc,
            },
        )

        if isinstance(code, SetupableActor):
            logger.info("setting up actor", actor=actor, code=code)
            await code.setup(actor)

        async def task():
            with self.curr.bind(context):
                ending = NT.Success
                try:
                    await code(*args)
                    self.yell.info(
                        "actor finished",
                        actor=context.addr,
                        actor_name=name,
                    )

                except BaseException as e:
                    logger.error(
                        "actor crashed",
                        actor=context.addr,
                        actor_name=name,
                        error=e,
                        parent=context.boss,
                    )

                    ending = NT.Failure

                    if parent_ctx and parent_ctx.trap:
                        self.yell.info(
                            "sending exit signal",
                            to=parent_ctx.addr,
                        )
                        await self.send_exit_signal(
                            parent_ctx.addr, context.addr, e
                        )
                    else:
                        self.yell.info("raising exception")
                        raise
                finally:
                    self.yell.info(
                        "deleting actor", actor=(context.addr, name)
                    )
                    ending = blank(ending)
                    now = Literal(datetime.now(UTC), datatype=XSD.dateTime)
                    add(ending, {PROV.atTime: now})
                    add(actor_proc, {PROV.wasEndedBy: ending})

                    # Since our actors have no permanent identity, we mark it as
                    # invalidated by the ending of the process.
                    #
                    # When we implement permanent identities, an actor will be
                    # realized in multiple processes, so exiting a process will
                    # not invalidate the actor itself.
                    #
                    # Also when a supervisor restarts an actor, maybe we should
                    # not invalidate the actor...

                    add(actor, {PROV.wasInvalidatedBy: ending})
                    del self.deck[context.addr]
                    self.print_actor_tree()

        crib.start_soon(task)
        return context.addr

    async def send_exit_signal(
        self, parent: URIRef, child: URIRef, error: BaseException
    ):
        with with_transient_graph() as id:
            new(
                NT.Exit,
                {NT.actor: child, NT.message: Literal(str(error))},
                id,
            )

            child_ctx = self.deck.get(child)
            child_name = child_ctx.name if child_ctx else "unknown"
            self.yell.info(
                "sending exit signal",
                to=parent,
                child=child,
                child_name=child_name,
                error=error,
            )

            await self.send(parent)

    def get_actor_hierarchy(self) -> Dict[URIRef, Set[URIRef]]:
        """Get the parent-child relationships between actors."""
        kids = defaultdict(set)
        for addr, ctx in self.deck.items():
            if ctx.boss != ctx.addr:  # Skip root which is its own parent
                kids[ctx.boss].add(addr)
        return dict(kids)

    def format_actor_tree(
        self, root: URIRef, indent: str = "", is_last: bool = True
    ) -> str:
        """Format the actor hierarchy as a tree string starting from given root."""
        ctx = self.deck.get(root)
        if not ctx:
            return f"{indent}[deleted actor {root}]\n"

        marker = "└── " if is_last else "├── "
        result = f"{indent}{marker}{ctx.name} ({root})\n"

        children = self.get_actor_hierarchy().get(root, set())
        child_list = sorted(children)  # Sort for consistent output

        for i, child in enumerate(child_list):
            is_last_child = i == len(child_list) - 1
            next_indent = indent + ("    " if is_last else "│   ")
            result += self.format_actor_tree(
                child, next_indent, is_last_child
            )

        return result

    def print_actor_tree(self):
        """Print the complete actor hierarchy tree."""
        # Find the root (actor that is its own parent)
        root = next(
            uri for uri, ctx in self.deck.items() if ctx.boss == ctx.addr
        )
        tree = self.format_actor_tree(root)
        self.yell.info("Actor hierarchy:\n" + tree)

    def link_actor_to_identity(self, actor: URIRef):
        """Create a graph linking an actor to this town's identity."""
        add(self.identity_uri, {PROV.started: actor})


vat = Parameter[Vat]("hub")


async def spawn(
    nursery: trio.Nursery,
    action: Callable,
    *args,
    name: Optional[str] = None,
):
    system = vat.get()
    return await system.spawn(nursery, action, *args, name=name)


def this() -> URIRef:
    return vat.get().this()


def boss() -> URIRef:
    return vat.get().curr.get().boss


def get_base() -> URIRef:
    """Get the base URI from the current actor system."""
    return vat.get().site[""]


def get_site() -> Namespace:
    """Get the site namespace from the current actor system."""
    return vat.get().site


async def send(actor: URIRef, message: Optional[Graph] = None):
    system = vat.get()
    if message is None:
        message = here.graph.get()
    logger.info("sending message", actor=actor, graph=message)
    await system.send(actor, message)


async def receive() -> Graph:
    system = vat.get()
    return await system.curr.get().recv.receive()


save_lock = trio.Lock()


async def persist(graph: Graph):
    logger.info("persisting graph", graph=graph)
    repo = context.repo.get()
    before_count = len(repo.dataset)

    graph_id = graph.identifier
    assert isinstance(graph_id, URIRef)

    repo_graph = repo.graph(graph_id)
    for s, p, o in graph:
        repo_graph.add((s, p, o))

    after_count = len(repo.dataset)

    async with save_lock:
        await repo.save_all()

    logger.info(
        "persisted graph",
        before=before_count,
        after=after_count,
        added=after_count - before_count,
        repo=repo,
        graph=graph,
    )


def create_graph(
    suffix: Optional[str] = None, *, base: Optional[str] = None
) -> Graph:
    """Create a new graph with standard bindings and optional suffix-based identifier.

    Args:
        suffix: Optional path suffix for the graph ID. If None, a fresh URI is minted.
        base: Optional base URI. If None, uses the current site.
    """
    site = get_site()
    base = base or str(site)

    if suffix is None:
        id = mint.fresh_uri(site)
    else:
        id = site[suffix]

    g = context.repo.get().dataset.graph(id, base)
    g.bind("nt", NT)
    g.bind("deepgram", DEEPGRAM)
    g.bind("site", site)
    g.bind("did", DID)
    g.bind("prov", PROV)

    return g


@asynccontextmanager
async def txgraph(graph: Optional[Graph] = None):
    g = create_graph()
    if graph is not None:
        g += graph

    with here.graph.bind(g):
        yield g

    await persist(g)
