# A global context variable for dependency injection of the current RDF graph.
# This enables a form of dynamic scoping where code can access the "current graph"
# without explicitly passing it through all function calls.
from contextlib import contextmanager
from typing import Any, Generator, Optional, Sequence, Generic, TypeVar
from rdflib import Graph, Literal


from contextvars import ContextVar

from bubble.mint import fresh_iri

from rdflib.graph import _TripleType, QuotedGraph

from bubble.prfx import AS, NT, SWA


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


graph = Parameter("graph", Graph())


def quote(triples: Sequence[_TripleType]) -> QuotedGraph:
    quoted = QuotedGraph(graph.get().store, fresh_iri())
    for subject, predicate, object in triples:
        quoted.add((subject, predicate, object))
    return quoted


def langstr(s: str) -> Literal:
    return Literal(s, lang="en")


def bind_prefixes():
    g = graph.get()
    g.bind("swa", SWA)
    g.bind("nt", NT)
    g.bind("as", AS)
