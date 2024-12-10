"""Utility functions for N3 processing."""

import sys

from typing import Any, Optional, overload

from rdflib import (
    RDF,
    BNode,
    Graph,
    URIRef,
    Literal,
    Namespace,
    IdentifiedNode,
)
from rdflib.graph import _ObjectType, _SubjectType, _PredicateType
from rdflib.query import ResultRow

import swash.vars as vars

from swash.mint import fresh_uri
from swash.prfx import AI, NT, JSON

S = _SubjectType
P = _PredicateType
O = _ObjectType  # noqa: E741


def print_n3(graph: Optional[Graph] = None) -> None:
    """Print the current graph in N3 format"""
    from rich import print
    from rich.panel import Panel
    from rich.syntax import Syntax

    g = graph if graph is not None else vars.graph.get()
    n3 = g.serialize(format="n3").replace("    ", "  ").strip()

    # only if connected to terminal do we use rich
    if sys.stdout.isatty():
        print(
            Panel(
                Syntax(n3, "turtle", theme="zenburn"),
            )
        )
    else:
        print(n3)


def graph_string(graph: Graph) -> str:
    """Serialize a graph to a string"""
    s = graph.serialize(format="trig").replace("    ", "  ").strip()
    return f"[id={graph.identifier}]\n{s}"


def get_single_subject(predicate, object, graph=None):
    """Get a single subject for a predicate-object pair from the current graph"""
    graph = graph if graph is not None else vars.graph.get()
    subjects = list(graph.subjects(predicate, object))
    if len(subjects) != 1:
        raise ValueError(f"Expected 1 subject, got {len(subjects)}")
    return subjects[0]


def get_single_object(subject, predicate, graph=None):
    """Get a single object for a subject-predicate pair from the current graph"""
    graph = graph if graph is not None else vars.graph.get()
    objects = list(graph.objects(subject, predicate))
    if len(objects) != 1:
        raise ValueError(f"Expected 1 object, got {len(objects)}")
    return objects[0]


def get_subjects(predicate, object):
    """Get all subjects for a predicate-object pair from the current graph"""
    g = vars.graph.get()
    return list(g.subjects(predicate, object))


def get_objects(subject, predicate):
    """Get all objects for a subject-predicate pair from the current graph"""
    g = vars.graph.get()
    return list(g.objects(subject, predicate))


class QueryError(Exception):
    pass


class NoResultsFoundError(QueryError):
    def __init__(
        self, query: str, bindings: dict, count: Optional[int] = None
    ):
        super().__init__(
            f"No results found for query: {query}\n\nBindings:\n{bindings}"
        )
        self.query = query
        self.bindings = bindings
        self.count = count


class MultipleResultsError(QueryError):
    pass


def select_one_row(query: str, bindings: dict = {}) -> ResultRow:
    """Select a single row from a query"""
    rows = select_rows(query, bindings)
    if len(rows) == 0:
        print(bindings)
        raise NoResultsFoundError(query, bindings)
    elif len(rows) != 1:
        raise MultipleResultsError(query, bindings, len(rows))
    return rows[0]


def select_rows(query: str, bindings: dict = {}) -> list[ResultRow]:
    """Select multiple rows from a query on the current graph"""
    results = vars.graph.get().query(
        query,
        initBindings=bindings,
        initNs={"nt": NT, "json": JSON, "ai": AI},
    )
    return [row for row in results if isinstance(row, ResultRow)]


def turtle(src: str) -> Graph:
    """Parse turtle data into the current graph"""
    with vars.graph.bind(Graph()) as graph:
        graph.parse(data=src, format="n3")
        graph.bind("nt", NT)
        return graph


def add(subject: S, properties: dict[P, Any]) -> None:
    graph = vars.graph.get()
    for predicate, object in properties.items():
        graph.add((subject, predicate, object))


@overload
def new(type: None = None, properties: dict[P, Any] = {}) -> S: ...
@overload
def new(
    type: S | None = None,
    properties: dict[P, Any] = {},
    subject: S | None = None,
) -> S: ...


def new(
    type: Optional[S] = None,
    properties: Optional[dict[P, Any]] = None,
    subject: Optional[S] = None,
) -> S:
    graph = vars.graph.get()

    if subject is None:
        subject = fresh_uri(graph)

    if type is not None:
        graph.add((subject, RDF.type, type))

    if properties is not None:
        for predicate, object in properties.items():
            if isinstance(object, list):
                for item in object:
                    o = item if isinstance(item, O) else Literal(item)
                    graph.add((subject, predicate, o))
            else:
                o = object if isinstance(object, O) else Literal(object)
                graph.add((subject, predicate, o))

    return subject


def is_a(subject: S, type: S, graph=None) -> bool:
    graph = graph if graph is not None else vars.graph.get()
    if isinstance(subject, IdentifiedNode):
        return type in graph.objects(subject, RDF.type)
    elif isinstance(subject, Literal):
        return subject.datatype == type
    else:
        raise ValueError(f"Unexpected subject type: {subject}")


def bubble(type: O, ns: Namespace, claims: dict[P, O] = {}) -> Graph:
    id = fresh_uri(ns)
    graph = Graph(identifier=id, base=str(ns))
    graph.bind("", id)
    graph.add((id, RDF.type, type))
    for predicate, object in claims.items():
        graph.add((graph.identifier, predicate, object))
    return graph
