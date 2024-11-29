# A global context variable for dependency injection of the current RDF graph.
# This enables a form of dynamic scoping where code can access the "current graph"
# without explicitly passing it through all function calls.
from contextlib import contextmanager
from typing import Sequence
from rdflib import Graph, Literal


from contextvars import ContextVar

from bubble.mint import fresh_iri

from rdflib.graph import _TripleType, QuotedGraph

from bubble.prfx import AS, NT, SWA


current_graph = ContextVar("graph", default=Graph())


@contextmanager
def binding(var: ContextVar, value):
    """Context manager for temporarily setting a context variable.

    Implements the dynamic scoping pattern - sets the value within the context
    and restores the previous value when exiting, even if an exception occurs.
    """
    token = var.set(value)
    try:
        yield value
    finally:
        var.reset(token)


@contextmanager
def using_graph(graph: Graph):
    """Temporarily set the current graph within a context.

    This is a convenience wrapper around using() for the common case
    of injecting a graph dependency.
    """
    with binding(current_graph, graph):
        yield graph


def quote(triples: Sequence[_TripleType]) -> QuotedGraph:
    quoted = QuotedGraph(current_graph.get().store, fresh_iri())
    for subject, predicate, object in triples:
        quoted.add((subject, predicate, object))
    return quoted


def langstr(s: str) -> Literal:
    return Literal(s, lang="en")


def bind_prefixes():
    g = current_graph.get()
    g.bind("swa", SWA)
    g.bind("nt", NT)
    g.bind("as", AS)
