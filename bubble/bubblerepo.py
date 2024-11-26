# This module implements a repository of RDF/N3 documents.
#
# It uses a local Git repository for storage.
#
# The default repository is $HOME/bubble.
#
# If the repository is empty, it will be initialized as a new bubble.
# Each bubble has a unique IRI minted on creation.

import logging
import tempfile


import trio

from trio import Path
from rdflib import (
    RDF,
    Graph,
    URIRef,
)
from rdflib.graph import _SubjectType

from bubble.bubbleboot import describe_new_bubble
from bubble.gensym import Mint, mintvar
from bubble.ns import NT
from bubble.rdfutil import get_single_subject

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
        paths = list(await directory.glob(pattern))

        for path in paths:
            logger.info(f"Loading {kind} from {path}")
            self.graph.parse(path)

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
        from bubble.rdfutil import reason

        tmpfile = Path(tempfile.gettempdir()) / "bubble.n3"
        self.graph.serialize(destination=tmpfile, format="n3")
        logger.info(f"Reasoning over {tmpfile}")
        conclusion = await reason([str(tmpfile)])
        logger.info(f"Conclusion has {len(conclusion)} triples")
        return conclusion

    @staticmethod
    async def open(path: Path, mint: Mint) -> "BubbleRepo":
        if not await path.exists():
            await path.mkdir(parents=True)

        if not await (path / "root.n3").exists():
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
        if not await self.workdir.joinpath(".git").exists():
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
