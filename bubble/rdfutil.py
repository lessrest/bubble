"""Utility functions for N3 processing."""

from typing import Any, Optional, Sequence

import trio

from rdflib import RDF, Graph, Literal
from rdflib.graph import _ObjectType, _SubjectType, _PredicateType
from rdflib.query import ResultRow

from bubble.gensym import fresh_uri
from bubble.graphvar import graphvar
from bubble.ns import NT, SWA, JSON


S = _SubjectType
P = _PredicateType
O = _ObjectType


class New:
    """Create new nodes in a graph, inspired by Turtle syntax"""

    def __init__(self, graph: Graph):
        self.graph = graph

    def __call__(
        self,
        type: Optional[S] = None,
        properties: dict[P, Any] = {},
        subject: Optional[S] = None,
    ) -> S:
        if subject is None:
            subject = fresh_uri(SWA)

        if type is not None:
            self.graph.add((subject, RDF.type, type))

        if properties is not None:
            for predicate, object in properties.items():
                if isinstance(object, list):
                    for item in object:
                        o = (
                            item
                            if isinstance(item, O)
                            else Literal(item)
                        )
                        self.graph.add((subject, predicate, o))
                else:
                    o = (
                        object
                        if isinstance(object, O)
                        else Literal(object)
                    )
                    self.graph.add((subject, predicate, o))

        return subject


def print_n3() -> None:
    """Print the current graph in N3 format"""
    from rich import print
    from rich.panel import Panel
    from rich.syntax import Syntax

    n3 = graphvar.get().serialize(format="n3").replace("    ", "  ").strip()

    print(
        Panel(
            Syntax(n3, "turtle", theme="zenburn"),
        )
    )


def get_single_subject(predicate, object):
    """Get a single subject for a predicate-object pair from the current graph"""
    subjects = get_subjects(graphvar.get(), predicate, object)
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


def select_one_row(query: str, bindings: dict = {}) -> ResultRow:
    """Select a single row from a query"""
    rows = select_rows(query, bindings)
    if len(rows) != 1:
        raise ValueError("No result row found")
    return rows[0]


def select_rows(query: str, bindings: dict = {}) -> list[ResultRow]:
    """Select multiple rows from a query"""
    results = graphvar.get().query(
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


def new(*args, **kwargs):
    return New(graphvar.get())(*args, **kwargs)
