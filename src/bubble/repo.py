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

import structlog
import trio

from trio import Path
from rdflib import (
    RDF,
    Graph,
    URIRef,
    Dataset,
)
from rdflib.graph import _SubjectType

from bubble.boot import describe_new_bubble
from swash.mind import reason
from swash.prfx import NT
from swash.util import get_single_subject, print_n3
from swash import vars
from bubble.blob import BlobStore, BlobStream

logger = structlog.get_logger()


@dataclass
class BubbleRepo:
    """A repository of RDF/N3 documents"""

    # The path to the bubble's root directory
    workdir: Path

    # The path to the bubble's root.n3 file
    rootpath: Path

    # The bubble's IRI
    bubble: _SubjectType

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
        self.bubble = base

        self.dataset = dataset
        self.graph = self.dataset.graph(NT.bubble)
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

    @staticmethod
    async def open(path: Path) -> "BubbleRepo":
        if not await trio.Path(path).exists():
            logger.info("creating bubble", path=str(path))
            await trio.Path(path).mkdir(parents=True)

        should_commit = False

        if not await trio.Path(path / "root.n3").exists():
            logger.info("describing new bubble", path=str(path))
            graph = await describe_new_bubble(path)
            graph.serialize(destination=path / "root.n3", format="n3")
            should_commit = True

        dataset = Dataset(default_union=True)

        logger.info("parsing root.n3", path=str(path / "root.n3"))
        with vars.graph.bind(
            Graph().parse(path / "root.n3", format="n3")
        ) as graph:
            bubble = get_single_subject(RDF.type, NT.Bubble)
            bubble_graph = dataset.graph(NT.bubble)
            for triple in graph:
                bubble_graph.add(triple)

        repo = BubbleRepo(path, dataset, URIRef(bubble))
        logger.info("created repo", repo=repo)
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

        # Add all files to the index
        await trio.run_process(
            ["git", "-C", str(self.workdir), "add", "root.n3"],
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
