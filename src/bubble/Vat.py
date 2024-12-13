from contextlib import contextmanager
from dataclasses import dataclass
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
from rdflib import PROV, Graph, Literal, Namespace, URIRef
from swash import Parameter, mint, vars
from swash.prfx import DEEPGRAM, DID, NT
from swash.util import add, new


from collections import defaultdict
from typing import (
    Awaitable,
    Callable,
    Dict,
    Generator,
    MutableMapping,
    Optional,
    Set,
)


@dataclass
class ActorContext:
    boss: URIRef
    addr: URIRef
    send: trio.MemorySendChannel
    recv: trio.MemoryReceiveChannel
    trap: bool = False
    name: str = "anonymous"


def fresh_uri(site: Optional[Namespace] = None) -> URIRef:
    if site is None:
        site = vat.get().site
    return mint.fresh_uri(site)


def new_context(parent: URIRef, name: str = "unnamed") -> ActorContext:
    chan_send, chan_recv = trio.open_memory_channel(8)
    return ActorContext(
        parent, fresh_uri(), chan_send, chan_recv, name=name
    )


def root_context(site: Namespace, name: str = "root") -> ActorContext:
    uri = fresh_uri(site)
    chan_send, chan_recv = trio.open_memory_channel(8)
    return ActorContext(uri, uri, chan_send, chan_recv, name=name)


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

    g = Graph(base=base, identifier=id)
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
        self.deck[context.addr] = context

        self.yell.info(
            "spawning",
            actor=context.addr,
            actor_name=name,
            parent=parent_ctx.addr,
        )

        async def task():
            with self.curr.bind(context):
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
