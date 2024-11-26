# A global context variable for dependency injection of the current RDF graph.
# This enables a form of dynamic scoping where code can access the "current graph"
# without explicitly passing it through all function calls.
from contextlib import contextmanager
from rdflib import Graph, Literal


from contextvars import ContextVar

from bubble.gensym import fresh_iri

from rdflib.graph import _TripleType, QuotedGraph

from bubble.ns import AS, NT, SWA


graphvar = ContextVar("graph", default=Graph())


@contextmanager
def using(var: ContextVar, value):
    """Context manager for temporarily setting a context variable.

    Implements the dynamic scoping pattern - sets the value within the context
    and restores the previous value when exiting, even if an exception occurs.
    """
    try:
        token = var.set(value)
        yield value
    finally:
        var.reset(token)


@contextmanager
def using_graph(graph: Graph):
    """Temporarily set the current graph within a context.

    This is a convenience wrapper around using() for the common case
    of injecting a graph dependency.
    """
    with using(graphvar, graph):
        yield graph


def quote(triples: list[_TripleType]) -> QuotedGraph:
    quoted = QuotedGraph(graphvar.get().store, fresh_iri())
    for subject, predicate, object in triples:
        quoted.add((subject, predicate, object))
    return quoted


def langstr(s: str) -> Literal:
    return Literal(s, lang="en")


def bind_prefixes():
    g = graphvar.get()
    g.bind("swa", SWA)
    g.bind("nt", NT)
    g.bind("as", AS)
