# This module implements a repository of RDF/N3 documents.
#
# It uses a local Git repository for storage.
#
# The default repository is $HOME/bubble.
#
# If the repository is empty, it will be initialized as a new bubble.
# Each bubble has a unique IRI minted on creation.

from datetime import UTC, datetime
import trio

from trio import Path
from rdflib import RDF, XSD, Graph, Literal, URIRef

from bubble.id import Mint
from bubble.ns import NT, SWA
from bubble.n3_utils import get_single_subject


class Bubble:
    """A repository of RDF/N3 documents"""

    path: Path
    root: Path
    mint: Mint
    base: URIRef
    graph: Graph

    def __init__(self, path: Path, mint: Mint, base: URIRef):
        self.path = path
        self.root = path / "root.n3"
        self.mint = mint
        self.base = base

        self.graph = Graph(base=base, identifier=base)
        self.graph.parse(self.root, format="n3")

    @staticmethod
    async def open(path: Path, mint: Mint) -> "Bubble":
        if not await path.exists():
            raise ValueError(f"Bubble not found at {path}")

        if not await (path / "root.n3").exists():
            base = mint.fresh_secure_iri(SWA)
            graph = Graph(base=base, identifier=base)
            graph.bind("swa", SWA)
            graph.bind("nt", NT)

            graph.add((base, RDF.type, NT.Bubble))
            graph.add(
                (
                    base,
                    NT.created,
                    Literal(datetime.now(UTC), datatype=XSD.dateTime),
                )
            )

            head = mint.fresh_secure_iri(SWA)
            graph.add((base, NT.pointsTo, head))
            graph.add((head, RDF.type, NT.Step))
            graph.add((head, NT.ranks, Literal(1)))

            graph.serialize(destination=path / "root.n3", format="n3")
            bubble = Bubble(path, mint, base)
            await bubble.commit()
            return bubble

        else:
            graph = Graph()
            graph.parse(path / "root.n3", format="n3")

            base = get_single_subject(graph, RDF.type, NT.Bubble)

            assert isinstance(base, URIRef)

            return Bubble(path, mint, URIRef(base))

    async def commit(self) -> None:
        """Commit the bubble"""
        await trio.run_process(["git", "add", "."])
        await trio.run_process(
            ["git", "commit", "-m", f"Initialize {self.base}"]
        )
