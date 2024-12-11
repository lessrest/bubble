"""
A module for building RDF graphs using Python context managers.
Provides a declarative way to construct RDF graphs with a syntax similar to Turtle.
"""

from contextlib import _GeneratorContextManager, contextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Generator, Optional

from rdflib import (
    SKOS,
    BNode,
    Dataset,
    Graph,
    Literal,
    URIRef,
)
from rdflib.namespace import RDF, RDFS
from swash.util import O, S

from . import vars

# Context variable to track current subject
current_subject: ContextVar[Optional[S]] = ContextVar(
    "current_subject", default=None
)


@contextmanager
def graph():
    """Creates a new graph context for building RDF content"""
    with vars.graph.bind(Graph()) as g:
        yield g


@contextmanager
def new_dataset():
    """Creates a new dataset context for building RDF content"""
    with vars.dataset.bind(Dataset()) as g:
        with vars.graph.bind(g):
            yield g


class Subject:
    """Wrapper for a subject node that supports predicates"""

    def __init__(self, node: S):
        self.node = node

    @contextmanager
    def _as_current(self):
        """Temporarily set this subject as the current subject"""
        token = current_subject.set(self.node)
        try:
            yield
        finally:
            current_subject.reset(token)

    def add(self, pred: URIRef, obj: Any):
        """Add a predicate-object pair to this subject"""
        with self._as_current():
            property(pred, obj)


def resource(
    id: Optional[URIRef] = None,
    a: Optional[URIRef] = None,
) -> _GeneratorContextManager[Subject]:
    """
    Creates a new subject node in the graph.
    If 'a' is provided, adds an rdf:type triple.
    """
    s = Subject(id or BNode())
    token = current_subject.set(s.node)

    if a:
        g = vars.graph.get()
        g.add((s.node, RDF.type, a))

    @contextmanager
    def f() -> Generator[Subject, Any, None]:
        try:
            yield s
        finally:
            current_subject.reset(token)

    return f()


def property(
    pred: URIRef, obj: Optional[Any] = None
) -> _GeneratorContextManager[Subject]:
    """
    Start describing a new subject that will be connected via pred.
    Usage:
        with property(pred):
            a(type_uri)
            property(prop, value)
    """
    parent = current_subject.get()
    if parent is None:
        raise RuntimeError("No active subject context")

    if obj is None:
        obj = BNode()
    elif isinstance(obj, URIRef):
        obj = obj
    elif isinstance(obj, (str, int, float, bool, datetime)):
        obj = Literal(obj)
    elif isinstance(obj, Subject):
        obj = obj.node

    g = vars.graph.get()
    if g is None:
        raise RuntimeError("No active graph context")
    g.add((parent, pred, obj))

    @contextmanager
    def f():
        subj = Subject(obj)
        with subj._as_current():
            yield subj

    return f()


def label(text: str, lang: Optional[str] = "en"):
    property(RDFS.label, Literal(text, lang=lang))


def definition(text: str, lang: Optional[str] = "en"):
    property(SKOS.definition, Literal(text, lang=lang))


def note(text: str, lang: Optional[str] = "en"):
    property(SKOS.note, Literal(text, lang=lang))


def example(text: str, lang: Optional[str] = "en"):
    property(SKOS.example, Literal(text, lang=lang))


def a(type_uri: O):
    property(RDF.type, type_uri)


def subclass(class_uri: URIRef):
    """Add an RDFS subClassOf relation to the given class"""
    property(RDFS.subClassOf, class_uri)


def literal(
    value: Any,
    datatype: Optional[URIRef] = None,
    lang: Optional[str] = None,
):
    """Creates an RDF literal with optional datatype or language tag"""
    return Literal(value, datatype=datatype, lang=lang)
