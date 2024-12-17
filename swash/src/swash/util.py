"""Utility functions for N3 processing."""

import sys

from typing import Any, Optional, Sequence, overload

from rdflib import (
    RDF,
    XSD,
    BNode,
    Graph,
    Literal,
    Namespace,
    IdentifiedNode,
    URIRef,
)
from rdflib.collection import Collection
from rdflib.graph import _ObjectType, _SubjectType, _PredicateType
from rdflib.query import ResultRow

import swash.vars as vars

from swash.mint import fresh_uri
from swash.prfx import AI, NT, JSON

S = _SubjectType
P = _PredicateType
O = _ObjectType  # noqa: E741


def print_n3(
    graph: Optional[Graph] = None, title: Optional[str] = None
) -> None:
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
                title=title,
            )
        )
    else:
        print(n3)


def graph_string(graph: Graph) -> str:
    """Serialize a graph to a string"""
    s = graph.serialize(format="trig").replace("    ", "  ").strip()
    return (
        f"[id={graph.identifier}]\n[class={graph.__class__.__name__}]\n{s}"
    )


def get_single_object(subject: S, predicate: P, graph=None) -> O:
    """Get a single object for a subject-predicate pair from the current graph"""
    graph = graph if graph is not None else vars.graph.get()
    objects = list(graph.objects(subject, predicate))
    if len(objects) != 1:
        raise ValueError(f"Expected 1 object, got {len(objects)}")
    return objects[0]


def get_single_subject(predicate: P, object: O, graph=None) -> S:
    """Get a single subject for a predicate-object pair from the current graph"""
    graph = graph if graph is not None else vars.graph.get()
    subjects = list(graph.subjects(predicate, object))
    if len(subjects) != 1:
        raise ValueError(f"Expected 1 subject, got {len(subjects)}")
    return subjects[0]


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


def add(subject: S, properties: dict[P, Any] = {}) -> None:
    build_resource(subject, None, properties=properties)


@overload
def new(type: None = None, properties: dict[P, Any] = {}) -> URIRef: ...
@overload
def new(
    type: S | None = None,
    properties: dict[P, Any] = {},
    subject: URIRef | None = None,
) -> URIRef: ...


def new(
    type: Optional[S] = None,
    properties: Optional[dict[P, Any]] = None,
    subject: Optional[URIRef] = None,
) -> URIRef:
    if subject is None:
        subject = fresh_uri(vars.graph.get())
    return build_resource(subject, type, properties)


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


def decimal(value: float, precision: int = 2) -> Literal:
    """Create a decimal literal with the given value, rounded to specified precision"""
    return Literal(round(value, precision), datatype=XSD.decimal)


def make_list(
    seq: Sequence[O], subject: Optional[IdentifiedNode] = None
) -> IdentifiedNode:
    node = BNode() if subject is None else subject
    Collection(vars.graph.get(), node, list(seq))
    return node


@overload
def blank(type: None = None, properties: dict[P, Any] = {}) -> BNode: ...
@overload
def blank(
    type: S | None = None, properties: dict[P, Any] = {}
) -> BNode: ...


def blank(
    type: Optional[S] = None,
    properties: Optional[dict[P, Any]] = None,
) -> BNode:
    """Create a new blank node with optional type and properties.

    Args:
        type: Optional RDF type for the blank node
        properties: Optional dictionary of predicate-object pairs

    Returns:
        BNode: The newly created blank node
    """
    return build_resource(BNode(), type, properties)


def build_resource[Subject: S](
    subject: Subject,
    type: Optional[S] = None,
    properties: Optional[dict[P, Any]] = None,
) -> Subject:
    """Build a resource with optional type and properties.

    Args:
        subject: The subject node to build upon
        type: Optional RDF type for the resource
        properties: Optional dictionary of predicate-object pairs

    Returns:
        The subject node with added properties
    """
    graph = vars.graph.get()

    if type is not None:
        graph.add((subject, RDF.type, type))

    if properties is not None:
        for predicate, object in properties.items():
            if isinstance(object, list) or isinstance(object, set):
                # TODO: list should mean rdf list
                for item in object:
                    o = item if isinstance(item, O) else Literal(item)
                    graph.add((subject, predicate, o))
            else:
                o = object if isinstance(object, O) else Literal(object)
                graph.add((subject, predicate, o))

    return subject
