"""Utility functions for N3 processing."""

from typing import Any, Optional


from rdflib import RDF, Graph, IdentifiedNode, Literal
from rdflib.graph import _ObjectType, _SubjectType, _PredicateType
from rdflib.query import ResultRow

from bubble.mint import fresh_uri
from bubble.vars import current_graph, using_graph
from bubble.prfx import NT, SWA, JSON


S = _SubjectType
P = _PredicateType
O = _ObjectType  # noqa: E741


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


def print_n3(graph: Optional[Graph] = None) -> None:
    """Print the current graph in N3 format"""
    from rich import print
    from rich.panel import Panel
    from rich.syntax import Syntax

    g = graph if graph is not None else current_graph.get()
    n3 = g.serialize(format="n3").replace("    ", "  ").strip()

    print(
        Panel(
            Syntax(n3, "turtle", theme="zenburn"),
        )
    )


def get_single_subject(predicate, object):
    """Get a single subject for a predicate-object pair from the current graph"""
    subjects = get_subjects(predicate, object)
    if len(subjects) != 1:
        raise ValueError(f"Expected 1 subject, got {len(subjects)}")
    return subjects[0]


def get_subjects(predicate, object):
    """Get all subjects for a predicate-object pair from the current graph"""
    g = current_graph.get()
    return list(g.subjects(predicate, object))


def select_one_row(query: str, bindings: dict = {}) -> ResultRow:
    """Select a single row from a query"""
    rows = select_rows(query, bindings)
    if len(rows) != 1:
        raise ValueError("No result row found")
    return rows[0]


def select_rows(query: str, bindings: dict = {}) -> list[ResultRow]:
    """Select multiple rows from a query on the current graph"""
    results = current_graph.get().query(
        query, initBindings=bindings, initNs={"nt": NT, "json": JSON}
    )
    return [row for row in results if isinstance(row, ResultRow)]


def turtle(src: str) -> Graph:
    """Parse turtle data into the current graph"""
    with using_graph(Graph()) as graph:
        graph.parse(data=src, format="n3")
        graph.bind("nt", NT)
        return graph


def new(*args, **kwargs):
    return New(current_graph.get())(*args, **kwargs)


def is_a(subject: S, type: S) -> bool:
    if isinstance(subject, IdentifiedNode):
        return type in current_graph.get().objects(subject, RDF.type)
    elif isinstance(subject, Literal):
        return subject.datatype == type
    else:
        raise ValueError(f"Unexpected subject type: {subject}")
