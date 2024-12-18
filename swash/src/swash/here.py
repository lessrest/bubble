# A global context variable for dependency injection of the current RDF graph.
# This enables a form of dynamic scoping where code can access the "current graph"
# without explicitly passing it through all function calls.
from typing import Any, Generic, TypeVar, Optional, Sequence, Generator
from contextlib import contextmanager
from contextvars import ContextVar

from rdflib import PROV, BNode, Graph, URIRef, Dataset, Literal, Namespace
from rdflib.graph import QuotedGraph, _TripleType

from swash.mint import fresh_iri
from swash.prfx import AS, NT, DID, SWA

T = TypeVar("T")


class Parameter(Generic[T]):
    """A class that manages a context variable with binding capability."""

    _var: ContextVar[T]

    def __init__(self, name: str, default: Optional[T] = None):
        if default is None:
            self._var = ContextVar(name)
        else:
            self._var = ContextVar(name, default=default)

    def get(self, default: Optional[T] = None) -> T:
        """Get the current value, raising an error if it is not set."""
        if default is None:
            return self._var.get()
        else:
            return self._var.get(default)

    @contextmanager
    def bind(self, value: T) -> Generator[T, Any, None]:
        """Temporarily bind a new value."""
        token = self._var.set(value)
        try:
            yield value
        finally:
            self._var.reset(token)

    def set(self, value: T):
        self._var.set(value)


graph: Parameter[Graph] = Parameter("graph", Graph())
dataset: Parameter[Dataset] = Parameter("dataset", None)
site: Parameter[Namespace] = Parameter("site")


@contextmanager
def in_graph(g: Graph):
    with graph.bind(g):
        yield g


def quote(triples: Sequence[_TripleType]) -> QuotedGraph:
    quoted = QuotedGraph(graph.get().store, fresh_iri())
    for subject, predicate, object in triples:
        quoted.add((subject, predicate, object))
    return quoted


def langstr(s: str) -> Literal:
    return Literal(s, lang="en")


def bind_prefixes(g: Graph):
    g.bind("swa", SWA)
    g.bind("nt", NT)
    g.bind("as", AS)
    g.bind("prov", PROV)
    g.bind("did", DID)
    g.bind("as", AS)


# Context variable to track current subject
current_subject: ContextVar[Optional[URIRef | BNode]] = ContextVar(
    "current_subject", default=None
)
