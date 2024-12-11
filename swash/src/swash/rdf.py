"""
A module for building RDF graphs using Python context managers.
Provides a declarative way to construct RDF graphs with a syntax similar to Turtle.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Optional, Union

from rdflib import (
    SKOS,
    BNode,
    Graph,
    Literal,
    URIRef,
)
from rdflib.namespace import RDF, RDFS
from swash.util import O

from . import vars

# Context variable to track current subject
current_subject: ContextVar[Optional[Union[URIRef, BNode]]] = ContextVar(
    "current_subject", default=None
)


@contextmanager
def graph():
    """Creates a new graph context for building RDF content"""
    with vars.graph.bind(Graph()) as g:
        yield g


@contextmanager
def new(type_uri: Optional[Union[URIRef, str]] = None):
    """
    Creates a new subject node in the graph.
    If type_uri is provided, adds an rdf:type triple.
    """
    subj = Subject(BNode())
    token = current_subject.set(subj.node)

    if type_uri:
        if isinstance(type_uri, str):
            type_uri = URIRef(type_uri)
        g = vars.graph.get()
        g.add((subj.node, RDF.type, type_uri))

    try:
        yield subj
    finally:
        current_subject.reset(token)


class Subject:
    """Wrapper for a subject node that supports predicates"""

    def __init__(self, node: Union[URIRef, BNode]):
        self.node = node

    @contextmanager
    def _as_current(self):
        """Temporarily set this subject as the current subject"""
        token = current_subject.set(self.node)
        try:
            yield
        finally:
            current_subject.reset(token)

    def has(self, pred: Union[str, URIRef], obj: Any):
        """Add a predicate-object pair to this subject"""
        with self._as_current():
            has(pred, obj)


@contextmanager
def add(pred: Union[str, URIRef]):
    """
    Start describing a new subject that will be connected via pred.
    Usage:
        with add(pred) as obj:
            a(type_uri)
            has(prop, value)
    """
    pred = pred if isinstance(pred, URIRef) else URIRef(pred)
    parent = current_subject.get()
    if parent is None:
        raise RuntimeError("No active subject context")

    subj = Subject(BNode())
    g = vars.graph.get()
    if g is None:
        raise RuntimeError("No active graph context")
    g.add((parent, pred, subj.node))
    with subj._as_current():
        yield subj


def has(pred: Union[str, URIRef], obj: Any):
    """Add a triple with the current subject"""
    graph = vars.graph.get()
    if graph is None:
        raise RuntimeError("No active graph context")

    subj = current_subject.get()
    if subj is None:
        raise RuntimeError("No active subject context")

    if isinstance(pred, str):
        pred = URIRef(pred)

    if isinstance(obj, URIRef):
        pass
    elif isinstance(obj, (str, int, float, bool)):
        obj = Literal(obj)
    elif isinstance(obj, str):
        obj = URIRef(obj)
    elif isinstance(obj, Subject):
        obj = obj.node

    graph.add((subj, pred, obj))


def label(text: str, lang: Optional[str] = "en"):
    has(RDFS.label, Literal(text, lang=lang))


def definition(text: str, lang: Optional[str] = "en"):
    has(SKOS.definition, Literal(text, lang=lang))


def note(text: str, lang: Optional[str] = "en"):
    has(SKOS.note, Literal(text, lang=lang))


def example(text: str, lang: Optional[str] = "en"):
    has(SKOS.example, Literal(text, lang=lang))


def a(type_uri: O):
    has(RDF.type, type_uri)


def subclass(class_uri: Union[str, URIRef]):
    """Add an RDFS subClassOf relation to the given class"""
    if isinstance(class_uri, str):
        class_uri = URIRef(class_uri)
    has(RDFS.subClassOf, class_uri)


def literal(
    value: Any,
    datatype: Optional[URIRef] = None,
    lang: Optional[str] = None,
):
    """Creates an RDF literal with optional datatype or language tag"""
    return Literal(value, datatype=datatype, lang=lang)
