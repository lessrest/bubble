from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

import tenacity
from bubble.data import context
from bubble.keys import (
    create_identity_graph,
    generate_identity_uri,
    generate_keypair,
    get_public_key_bytes,
    get_public_key_hex,
)


import structlog
import trio
from cryptography.hazmat.primitives.asymmetric import ed25519
from rdflib import (
    OWL,
    PROV,
    RDF,
    RDFS,
    XSD,
    Graph,
    Literal,
    Namespace,
    URIRef,
)
from swash import Parameter, mint, vars
from swash.prfx import DEEPGRAM, DID, NT
from swash.util import P, add, new, blank


from collections import defaultdict
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Generator,
    MutableMapping,
    Optional,
    Set,
)


logger = structlog.get_logger()


@dataclass
class ActorContext:
    boss: URIRef
    addr: URIRef
    proc: URIRef
    send: trio.MemorySendChannel
    recv: trio.MemoryReceiveChannel
    name: str = "anonymous"
    trap: bool = False


def fresh_uri(site: Optional[Namespace] = None) -> URIRef:
    if site is None:
        site = vat.get().site
    return mint.fresh_uri(site)


def new_context(parent: URIRef, name: str = "unnamed") -> ActorContext:
    chan_send, chan_recv = trio.open_memory_channel(8)
    return ActorContext(
        parent, fresh_uri(), fresh_uri(), chan_send, chan_recv, name=name
    )


def root_context(site: Namespace, name: str = "root") -> ActorContext:
    uri = fresh_uri(site)
    chan_send, chan_recv = trio.open_memory_channel(8)
    return ActorContext(uri, uri, uri, chan_send, chan_recv, name=name)


def get_site() -> Namespace:
    """Get the site namespace from the current actor system."""
    return vat.get().site


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

    logger.info("creating graph", id=id, base=base)

    #    g = Graph(base=base, identifier=id)
    g = context.repo.get().dataset.graph(id, base)
    g.bind("nt", NT)
    g.bind("deepgram", DEEPGRAM)
    g.bind("site", site)
    g.bind("did", DID)
    g.bind("prov", PROV)

    return g


@contextmanager
def with_transient_graph(
    suffix: Optional[str] = None,
) -> Generator[URIRef, None, None]:
    """Create a temporary graph that won't be persisted."""
    g = create_graph(suffix)
    with vars.graph.bind(g):
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

    def __init__(
        self,
        site: str,
        yell: structlog.stdlib.BoundLogger,
    ):
        self.site = Namespace(site)
        self.yell = yell.bind(site=site)

        # Generate Ed25519 keypair
        self.private_key, self.public_key = generate_keypair()
        self.identity_uri = generate_identity_uri(self.public_key)
        self.yell.info("generated Ed25519 keypair")

        root = root_context(self.site)
        self.curr = Parameter("current_actor", root)
        self.deck = {root.addr: root}

    def get_base_url(self) -> str:
        return str(self.site[""])

    def get_public_key_bytes(self) -> bytes:
        """Get the raw bytes of the public key."""
        return get_public_key_bytes(self.public_key)

    def get_public_key_hex(self) -> str:
        """Get the hex representation of the public key."""
        return get_public_key_hex(self.public_key)

    def get_identity_uri(self) -> URIRef:
        """Get the URI of this town's cryptographic identity."""
        return self.identity_uri

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

        new(
            OWL.Class,
            {
                RDFS.label: Literal("actor process", lang="en"),
                RDFS.subClassOf: PROV.Activity,
            },
            subject=NT.ActorProcess,
        )
        new(
            OWL.Class,
            {
                RDFS.label: Literal("actor", lang="en"),
                RDFS.subClassOf: [PROV.Entity, PROV.SoftwareAgent],
            },
            subject=NT.Actor,
        )

        now = Literal(datetime.now(UTC), datatype=XSD.dateTime)

        new(
            NT.ActorProcess,
            {
                PROV.startedAtTime: now,
                PROV.wasAssociatedWith: parent_proc,
            },
            actor_proc,
        )

        new(
            NT.ActorIdentity,
            {
                RDFS.label: Literal(name, lang="en"),
                PROV.wasGeneratedBy: parent_proc,
                PROV.generatedAtTime: now,
                PROV.wasAssociatedWith: actor_proc,
            },
            actor,
        )

        async def task():
            with self.curr.bind(context):
                ending = blank(NT.Success)
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

                    ending = blank(NT.Failure)

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

    async def send(self, actor: URIRef, message: Optional[Graph] = None):
        if message is None:
            message = vars.graph.get()

        if actor not in self.deck:
            raise ValueError(f"Actor {actor} not found")

        await self.deck[actor].send.send(message)

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


def get_base() -> URIRef:
    """Get the base URI from the current actor system."""
    return vat.get().site[""]


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


async def send(actor: URIRef, message: Optional[Graph] = None):
    system = vat.get()
    if message is None:
        message = vars.graph.get()
    logger.info("sending message", actor=actor, graph=message)
    return await system.send(actor, message)


async def receive() -> Graph:
    system = vat.get()
    return await system.curr.get().recv.receive()


class ServerActor[State]:
    def __init__(self, state: State):
        self.state = state
        self.name = self.__class__.__name__
        self.stop = False

    async def __call__(self):
        """Main actor message processing loop with error handling."""
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
        pass

    async def handle(self, nursery: trio.Nursery, graph: Graph) -> Graph:
        raise NotImplementedError


save_lock = trio.Lock()


async def persist(graph: Graph):
    logger.info("persisting graph", graph=graph)
    repo = context.repo.get()
    before_count = len(repo.dataset)

    repo.dataset.add_graph(graph)
    for s, p, o in graph:
        repo.dataset.add((s, p, o, graph))
    after_count = len(repo.dataset)

    graph_id = graph.identifier
    assert isinstance(graph_id, URIRef)
    async with save_lock:
        await repo.save_graph(graph_id)

    logger.info(
        "persisted graph",
        before=before_count,
        after=after_count,
        added=after_count - before_count,
        repo=repo,
        graph=graph,
    )


@asynccontextmanager
async def txgraph(graph: Optional[Graph] = None):
    g = create_graph()
    if graph is not None:
        g += graph

    with vars.graph.bind(g):
        yield g

    await persist(g)


class SimpleSupervisor:
    """A simple supervisor that manages named actors."""

    def __init__(self, actors: dict[str, Callable]):
        """Initialize with a dictionary mapping names to actor constructors.

        Args:
            actors: Dictionary mapping actor names to their constructor callables
        """
        self.actors = actors

    async def __call__(self):
        async with txgraph():
            new(NT.Supervisor, {}, this())

        def retry_sleep(retry_state: tenacity.RetryCallState) -> Any:
            return logger.warning(
                "supervised actor tree crashed; retrying after exponential backoff",
                retrying=retry_state,
            )

        async with trio.open_nursery() as nursery:
            for name, actor in self.actors.items():
                # retry = tenacity.AsyncRetrying(
                #     wait=tenacity.wait_exponential(multiplier=1, max=60),
                #     retry=tenacity.retry_if_exception_type(
                #         (trio.Cancelled, BaseExceptionGroup)
                #     ),
                #     before_sleep=retry_sleep,
                # )

                #                async for attempt in retry:
                #                   with attempt:
                logger.info(
                    "starting supervised actor", actor=actor, name=name
                )
                child = await spawn(nursery, actor, name=name)
                add(this(), {NT.supervises: child})


async def call(actor: URIRef, payload: Optional[Graph] = None) -> Graph:
    if payload is None:
        payload = vars.graph.get()

    sendchan, recvchan = trio.open_memory_channel[Graph](1)

    tmp = fresh_uri()
    vat.get().deck[tmp] = ActorContext(
        boss=this(),
        proc=this(),
        addr=tmp,
        send=sendchan,
        recv=recvchan,
    )

    payload.add((payload.identifier, NT.replyTo, tmp))

    logger.info(
        "sending request",
        actor=actor,
        graph=payload,
    )

    await send(actor, payload)

    return await recvchan.receive()


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
    """Actor that tracks and reports uptime since its creation."""

    async def init(self):
        self.state = datetime.now(UTC)
        async with txgraph():
            new(NT.UptimeActor, {}, this())

    async def handle(self, nursery, graph: Graph) -> Graph:
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
