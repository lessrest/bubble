# This module implements a repository of RDF/N3 documents.
#
# It uses a local Git repository for storage.
#
# The default repository is $HOME/bubble.
#
# If the repository is empty, it will be initialized as a new bubble.
# Each bubble has a unique IRI minted on creation.

from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
import logging
from dataclasses import dataclass

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
from bubble.mind import reason
from bubble.prfx import NT
from bubble.util import get_single_subject, print_n3
from bubble.vars import binding, using_graph

logger = logging.getLogger(__name__)


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

    def __init__(
        self, path: Path, dataset: Dataset, base: _SubjectType
    ):
        self.workdir = path
        self.rootpath = path / "root.n3"
        self.bubble = base

        self.dataset = dataset
        self.graph = self.dataset.graph(NT.bubble)
        self.vocab = self.dataset.graph(NT.vocabulary)

    async def load_many(
        self,
        directory: Path,
        pattern: str,
        kind: str,
    ) -> None:
        """Load files into the graph

        Args:
            directory: Directory to glob from
            pattern: Glob pattern to match
            kind: Description of what's being loaded for logging
        """
        paths = []
        files = await trio.Path(directory).glob(pattern)
        paths.extend(files)

        for path in paths:
            logger.info(f"Loading {kind} from {path}")
            self.graph.parse(str(path))

    async def load(self, path: Path) -> None:
        """Load the graph from a file"""
        await self.load_many(path.parent, path.name, "graph")

    async def load_ontology(self) -> None:
        """Load the ontology into the vocab graph"""
        vocab_dir = Path(__file__).parent.parent / "vocab"
        paths = []
        files = await trio.Path(vocab_dir).glob("*.ttl")
        paths.extend(files)

        # clear any existing vocabulary
        for triple in self.vocab:
            logger.info(f"Removing ontology triple for {triple[0]}")
            self.dataset.remove(triple)

        for path in paths:
            logger.info(f"Loading ontology from {path}")
            graph = Graph().parse(str(path), format="turtle")
            for s, p, o in graph:
                self.dataset.add((s, p, o, self.vocab))

    async def load_surfaces(self) -> None:
        """Load all surfaces from the bubble into the graph"""
        await self.load_many(self.workdir, "*.n3", "surface")

    async def load_rules(self) -> None:
        """Load all rules from the system rules directory"""
        rules_dir = Path(__file__).parent / "rule"
        await self.load_many(rules_dir, "*.n3", "rule")

    async def reason(self) -> Graph:
        """Reason over the graphs"""
        # Pass all graphs from dataset to the reasoner
        conclusion = await reason(list(self.dataset.graphs()))
        logger.info(f"Conclusion has {len(conclusion)} triples")
        return conclusion

    @staticmethod
    async def open(path: Path) -> "BubbleRepo":
        if not await trio.Path(path).exists():
            await trio.Path(path).mkdir(parents=True)

        should_commit = False

        if not await trio.Path(path / "root.n3").exists():
            graph = await describe_new_bubble(path)
            graph.serialize(destination=path / "root.n3", format="n3")
            should_commit = True

        dataset = Dataset(default_union=True)

        with using_graph(
            Graph().parse(path / "root.n3", format="n3")
        ) as graph:
            bubble = get_single_subject(RDF.type, NT.Bubble)
            bubble_graph = dataset.graph(NT.bubble)
            for triple in graph:
                bubble_graph.add(triple)

        repo = BubbleRepo(path, dataset, URIRef(bubble))

        if should_commit:
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
            ["git", "-C", str(self.workdir), "add", "."],
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


current_bubble: ContextVar[BubbleRepo] = ContextVar("bubble")


@contextmanager
def using_bubble(bubble: BubbleRepo):
    with binding(current_bubble, bubble):
        with using_graph(bubble.graph):
            yield bubble


@asynccontextmanager
async def using_bubble_at(path: Path):
    repo = await BubbleRepo.open(path)
    print_n3(repo.graph)
    with using_bubble(repo):
        yield repo
