"""Utility functions for N3 processing."""

from typing import Optional, Sequence

import trio

from rdflib import RDF, BNode, Graph, Namespace
from rdflib.graph import _ObjectType, _SubjectType, _PredicateType
from rdflib.query import ResultRow

from bubble.id import Mint
from bubble.ns import NT, SWA, JSON


class New:
    """Create new nodes in a graph, inspired by Turtle syntax"""

    def __init__(self, graph: Graph, mint: Mint = Mint()):
        self.graph = graph
        self.mint = mint

    def __call__(
        self,
        type: Optional[_SubjectType] = None,
        properties: dict[
            _PredicateType, _ObjectType | list[_ObjectType]
        ] = {},
        subject: Optional[_SubjectType] = None,
    ) -> _SubjectType:
        if subject is None:
            subject = self.mint.fresh_secure_iri(SWA)

        if type is not None:
            self.graph.add((subject, RDF.type, type))

        if properties is not None:
            for predicate, object in properties.items():
                if isinstance(object, list):
                    for item in object:
                        self.graph.add((subject, predicate, item))
                else:
                    self.graph.add((subject, predicate, object))

        return subject


def print_n3(graph: Graph) -> None:
    """Print the graph in N3 format"""
    from rich import print
    from rich.panel import Panel
    from rich.syntax import Syntax

    n3 = graph.serialize(format="n3").replace("    ", "  ").strip()

    print(
        Panel(
            Syntax(n3, "turtle", theme="zenburn"),
        )
    )


def get_single_subject(graph: Graph, predicate, object):
    """Get a single subject for a predicate-object pair"""
    subjects = get_subjects(graph, predicate, object)
    if len(subjects) != 1:
        raise ValueError(f"Expected 1 subject, got {len(subjects)}")
    return subjects[0]


def get_subjects(graph: Graph, predicate, object):
    """Get all subjects for a predicate-object pair"""
    return list(graph.subjects(predicate, object))


async def reason(input_paths: Sequence[str]) -> Graph:
    """Run the EYE reasoner on N3 files and return the resulting graph"""
    cmd = ["eye", "--nope", "--pass", *input_paths]

    with trio.move_on_after(1):
        result = await trio.run_process(
            cmd, capture_stdout=True, capture_stderr=True, check=True
        )

    g = Graph()
    g.parse(data=result.stdout.decode(), format="n3")
    return g


def skolemize(
    g: Graph,
    namespace: str = "https://swa.sh/.well-known/genid/",
) -> Graph:
    """Convert blank nodes in a graph to fresh IRIs"""
    mint = Mint()
    ns = Namespace(namespace)
    g_sk = Graph()

    # Copy namespace bindings
    for prefix, namespace in g.namespaces():
        g_sk.bind(prefix, namespace)
    g_sk.bind("id", ns)

    # Create mapping of blank nodes to IRIs
    bnode_map = {}

    def get_iri_for_bnode(bnode):
        if bnode not in bnode_map:
            bnode_map[bnode] = mint.fresh_secure_iri(ns)
        return bnode_map[bnode]

    # Copy all triples, consistently replacing blank nodes
    for s, p, o in g:
        s_new = get_iri_for_bnode(s) if isinstance(s, BNode) else s
        o_new = get_iri_for_bnode(o) if isinstance(o, BNode) else o
        g_sk.add((s_new, p, o_new))

    return g_sk


def select_one_row(
    graph: Graph, query: str, bindings: dict = {}
) -> ResultRow:
    """Select a single row from a query"""
    rows = select_rows(graph, query, bindings)
    if len(rows) != 1:
        raise ValueError("No result row found")
    return rows[0]


def select_rows(
    graph: Graph, query: str, bindings: dict = {}
) -> list[ResultRow]:
    """Select multiple rows from a query"""
    results = graph.query(
        query, initBindings=bindings, initNs={"nt": NT, "json": JSON}
    )
    rows = []
    for row in results:
        assert isinstance(row, ResultRow)
        rows.append(row)
    return rows


def turtle(src: str) -> Graph:
    graph = Graph()
    graph.parse(data=src, format="turtle")
    graph.bind("nt", NT)
    return graph
