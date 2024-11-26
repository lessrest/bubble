# This module implements a repository of RDF/N3 documents.
#
# It uses a local Git repository for storage.
#
# The default repository is $HOME/bubble.
#
# If the repository is empty, it will be initialized as a new bubble.
# Each bubble has a unique IRI minted on creation.

from rdflib import RDF, Graph, Literal, URIRef
from trio import Path
import trio

from bubble.id import Mint
from bubble.ns import SWA, NT


class Bubble:
    """A repository of RDF/N3 documents"""

    path: Path
    root: Path
    mint: Mint
    base: URIRef

    def __init__(self, path: Path, mint: Mint, base: URIRef):
        self.path = path
        self.root = path / "root.n3"
        self.mint = mint
        self.base = base

    @staticmethod
    async def open(path: Path, mint: Mint) -> "Bubble":
        if not await path.exists():
            raise ValueError(f"Bubble not found at {path}")

        if not await (path / "root.n3").exists():
            base = mint.fresh_secure_iri(SWA)
            graph = Graph(base=base)
            graph.bind("swa", SWA)
            graph.bind("nt", NT)
            graph.add((base, RDF.type, NT.Bubble))
            graph.serialize(destination=path / "root.n3", format="n3")
            bubble = Bubble(path, mint, base)
            await bubble.commit()
            return bubble

        else:
            graph = Graph()
            graph.parse(path / "root.n3", format="n3")
            if graph.base is None:
                raise ValueError(f"Bubble at {path} is missing a base URI")
            return Bubble(path, mint, URIRef(graph.base))

    async def commit(self) -> None:
        """Commit the bubble"""
        await trio.run_process(["git", "add", "."])
        await trio.run_process(
            ["git", "commit", "-m", f"Initialize {self.base}"]
        )
