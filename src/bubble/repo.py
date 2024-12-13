# This module implements a repository of RDF/N3 documents.
#
# It uses a local Git repository for storage.
#
# The default repository is $HOME/bubble.
#
# If the repository is empty, it will be initialized as a new bubble.
# Each bubble has a unique IRI minted on creation.

from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import Optional

import structlog
import trio

from trio import Path
from rdflib import (
    RDF,
    Graph,
    URIRef,
    Dataset,
    VOID,
)
from rdflib.graph import _SubjectType

from bubble.boot import describe_new_bubble
from swash.mind import reason
from swash.prfx import NT
from swash.util import get_single_subject, print_n3
from swash import vars
from bubble.blob import BlobStore, BlobStream
from swash.mint import fresh_uri
from bubble.keys import generate_keypair, get_public_key_bytes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

logger = structlog.get_logger()


@dataclass
class BubbleRepo:
    """A repository of RDF/N3 documents"""

    # The path to the bubble's root directory
    workdir: Path

    # The path to the bubble's root.n3 file
    rootpath: Path

    # The path to the bubble's private key file
    keypath: Path

    # The bubble's IRI
    bubble: _SubjectType

    # The bubble's keypair
    private_key: Optional[ed25519.Ed25519PrivateKey]
    public_key: Optional[ed25519.Ed25519PublicKey]

    # The dataset containing all graphs
    dataset: Dataset

    # The graph of the bubble's data
    graph: Graph

    # The graph containing vocabulary/ontology
    vocab: Graph

    # The graph containing transient data
    transient: Graph

    # The graph containing pending data
    pending: Graph

    # The blob store for binary data
    blobs: BlobStore

    def __init__(self, path: Path, dataset: Dataset, base: _SubjectType):
        self.workdir = path
        self.rootpath = path / "root.n3"
        self.keypath = path / "bubble.key"
        self.bubble = base
        self.private_key = None
        self.public_key = None

        self.dataset = dataset
        self.graph = self.dataset.graph(NT.bubble, base=base)
        self.vocab = self.dataset.graph(NT.vocabulary)
        self.transient = self.dataset.graph(NT.transient)
        self.pending = self.dataset.graph(NT.pending)
        self.blobs = BlobStore(str(path / "blobs.db"))

    def blob(self, stream_id: URIRef, seq: int = 0) -> BlobStream:
        """Get a blob stream by ID"""
        return self.blobs.stream(stream_id, seq)

    def get_streams_with_blobs(self) -> list[URIRef]:
        """Get list of stream IDs that have blobs stored"""
        return self.blobs.get_streams_with_blobs()

    async def load_many(
        self,
        directory: Path,
        pattern: str,
        kind: str,
        graph: Graph,
    ) -> None:
        """Load files into the graph

        Args:
            directory: Directory to glob from
            pattern: Glob pattern to match
            kind: Description of what's being loaded for logging
        """
        paths: list[Path] = []
        files = await trio.Path(directory).glob(pattern)
        paths.extend(files)

        for path in paths:
            logger.info(
                "Loading triples",
                kind=kind,
                source=path.as_uri(),
                graph=graph.identifier,
            )
            graph.parse(str(path))

    async def load_ontology(self) -> None:
        """Load the ontology into the vocab graph"""
        vocab_dir = Path(__file__).parent.parent.parent / "vocab"
        paths = []
        files = await trio.Path(vocab_dir).glob("*.ttl")
        paths.extend(files)

        # clear any existing vocabulary
        for triple in self.vocab:
            self.dataset.remove(triple)

        for path in paths:
            logger.info(
                "Loading triples",
                kind="ontology",
                source=path.as_uri(),
                graph=self.vocab.identifier,
            )
            graph = Graph().parse(str(path), format="turtle")
            for s, p, o in graph:
                self.dataset.add((s, p, o, self.vocab))

    async def load_surfaces(self) -> None:
        """Load all surfaces from the bubble into the graph"""
        await self.load_many(self.workdir, "root.n3", "surface", self.graph)

    async def load_rules(self) -> None:
        """Load all rules from the system rules directory"""
        rules_dir = Path(__file__).parent / "rule"
        # TODO: test this
        await self.load_many(rules_dir, "*.n3", "rule", self.vocab)

    async def reason(self) -> Graph:
        """Reason over the graphs"""
        # Pass all graphs from dataset to the reasoner
        conclusion = await reason(list(self.dataset.graphs()))
        logger.info(f"Conclusion has {len(conclusion)} triples")
        return conclusion

    async def load_keypair(self) -> None:
        """Load the bubble's keypair from disk."""
        if not await self.keypath.exists():
            return

        key_bytes = await self.keypath.read_bytes()
        self.private_key = ed25519.Ed25519PrivateKey.from_private_bytes(
            key_bytes
        )
        self.public_key = self.private_key.public_key()

    async def save_keypair(self) -> None:
        """Save the bubble's private key to disk."""
        if self.private_key is None:
            return

        key_bytes = self.private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        await self.keypath.write_bytes(key_bytes)
        # Set restrictive permissions on the key file
        await self.keypath.chmod(0o600)

    @staticmethod
    async def open(path: Path) -> "BubbleRepo":
        if not await trio.Path(path).exists():
            logger.info("creating bubble", path=str(path))
            await trio.Path(path).mkdir(parents=True)

        should_commit = False
        void_path = path / "void.ttl"

        if not await trio.Path(void_path).exists():
            logger.info("describing new bubble", path=str(path))
            # Generate keypair for new bubble
            private_key, public_key = generate_keypair()
            # Use site namespace for base and bubble URI
            bubble_uri = fresh_uri(vars.site.get())
            graph = await describe_new_bubble(path, bubble_uri, public_key)

            # Save the main graph
            graph.serialize(destination=path / "root.n3", format="n3")

            # Create void.ttl with just the bubble identifier
            void_graph = Graph()
            void_graph.add((bubble_uri, RDF.type, VOID.Dataset))
            void_graph.serialize(destination=void_path, format="turtle")

            # Create repo instance to save the keypair
            repo = BubbleRepo(
                path, Dataset(default_union=True), URIRef(bubble_uri)
            )
            repo.private_key = private_key
            repo.public_key = public_key
            await repo.save_keypair()

            should_commit = True
            return repo

        # Only load void.ttl to get the bubble identifier
        logger.info("loading void.ttl", path=str(void_path))
        void_graph = Graph().parse(void_path, format="turtle")
        bubble = get_single_subject(RDF.type, VOID.Dataset, void_graph)

        dataset = Dataset(default_union=True)
        repo = BubbleRepo(path, dataset, URIRef(bubble))
        await repo.load_keypair()

        if should_commit:
            logger.info("committing bubble", repo=repo)
            await repo.commit()

        return repo

    async def commit(self) -> None:
        """Commit the bubble"""
        if not await trio.Path(self.workdir / ".git").exists():
            await trio.run_process(
                ["git", "-C", str(self.workdir), "init"],
            )
            # Get the bubble's email address from its properties
            email = str(self.graph.value(self.bubble, NT.emailAddress))

            # Set Git configuration for this repository using the bubble's identity
            await trio.run_process(
                [
                    "git",
                    "-C",
                    str(self.workdir),
                    "config",
                    "user.name",
                    "Bubble",
                ],
            )
            await trio.run_process(
                [
                    "git",
                    "-C",
                    str(self.workdir),
                    "config",
                    "user.email",
                    email,
                ],
            )

        # Add both root.n3 and void.ttl to the index
        await trio.run_process(
            ["git", "-C", str(self.workdir), "add", "root.n3", "void.ttl"],
        )

        await trio.run_process(
            [
                "git",
                "-C",
                str(self.workdir),
                "commit",
                "-m",
                f"Initialize {self.bubble}",
            ]
        )

    async def save_graph(self) -> None:
        """Save the graph to the root file"""
        self.graph.serialize(destination=self.rootpath, format="n3")
        # await self.commit()

    @classmethod
    async def load(cls, path: Path) -> "BubbleRepo":
        """Open and fully initialize a BubbleRepo with all required data loaded."""
        bubble = await cls.open(path)
        await bubble.load_surfaces()
        await bubble.load_rules()
        await bubble.load_ontology()
        return bubble


current_bubble = vars.Parameter["BubbleRepo"]("bubble")


@contextmanager
def using_bubble(bubble: BubbleRepo):
    with current_bubble.bind(bubble):
        with vars.graph.bind(bubble.graph):
            with vars.dataset.bind(bubble.dataset):
                vars.bind_prefixes(bubble.graph)
                yield bubble


@asynccontextmanager
async def using_bubble_at(path: Path):
    repo = await BubbleRepo.open(path)
    print_n3(repo.graph)
    with using_bubble(repo):
        yield repo


@asynccontextmanager
async def loading_bubble_from(path: Path):
    logger.info("loading bubble", path=str(path))
    repo = await BubbleRepo.load(path)
    with using_bubble(repo):
        yield repo


async def save_bubble():
    await current_bubble.get().save_graph()
