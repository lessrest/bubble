# This module implements a repository of RDF/N3 documents.
#
# It uses a local Git repository for storage.
#
# The default repository is $HOME/bubble.
#
# If the repository is empty, it will be initialized as a new bubble.
# Each bubble has a unique IRI minted on creation.

import logging


import trio

from trio import Path
from rdflib import (
    RDF,
    Graph,
    URIRef,
)
from rdflib.graph import _SubjectType

from bubble.boot import describe_new_bubble
from bubble.mind import reason
from bubble.mint import Mint, mintvar
from bubble.prfx import NT
from bubble.util import get_single_subject

logger = logging.getLogger(__name__)


class BubbleRepo:
    """A repository of RDF/N3 documents"""

    # The path to the bubble's root directory
    workdir: Path

    # The path to the bubble's root.n3 file
    rootpath: Path

    # The mint used to generate IRIs
    minter: Mint

    # The bubble's IRI
    bubble: _SubjectType

    # The graph of the bubble
    graph: Graph

    def __init__(self, path: Path, base: _SubjectType):
        self.workdir = path
        self.rootpath = path / "root.n3"
        self.minter = mintvar.get()
        self.bubble = base
        self.graph = Graph()

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
        """Load the ontology into the graph"""
        vocab_dir = Path(__file__).parent.parent / "vocab"
        await self.load_many(vocab_dir, "*.ttl", "ontology")

    async def load_surfaces(self) -> None:
        """Load all surfaces from the bubble into the graph"""
        await self.load_many(self.workdir, "*.n3", "surface")

    async def load_rules(self) -> None:
        """Load all rules from the system rules directory"""
        rules_dir = Path(__file__).parent / "rules"
        await self.load_many(rules_dir, "*.n3", "rules")

    async def reason(self) -> Graph:
        """Reason over the graph"""
        conclusion = await reason([self.graph])
        logger.info(f"Conclusion has {len(conclusion)} triples")
        return conclusion

    @staticmethod
    async def open(path: Path, mint: Mint) -> "BubbleRepo":
        if not await trio.Path(path).exists():
            await trio.Path(path).mkdir(parents=True)

        if not await trio.Path(path / "root.n3").exists():
            bubble = await describe_new_bubble(path)
            repo = BubbleRepo(path, bubble)
            await repo.commit()
            return repo

        else:
            g = Graph()
            g.parse(path / "root.n3", format="n3")

            bubble = get_single_subject(RDF.type, NT.Bubble)

            assert isinstance(bubble, URIRef)
            return BubbleRepo(path, URIRef(bubble))

    async def commit(self) -> None:
        """Commit the bubble"""
        if not await trio.Path(self.workdir / ".git").exists():
            await trio.run_process(
                ["git", "-C", str(self.workdir), "init"],
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
