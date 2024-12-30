from rdflib import Graph, URIRef
from rdflib.graph import QuotedGraph

from swash import here


def test_graph_context():
    """Test that binding properly manages graph context"""
    test_graph = Graph(base="https://example.com/")
    test_graph.add((URIRef("s"), URIRef("p"), URIRef("o")))
    assert here.graph.get() != test_graph

    with here.graph.bind(test_graph) as g:
        assert g == test_graph
        assert here.graph.get() == test_graph

    assert here.graph.get() != test_graph


def test_nested_graph_context():
    """Test nested graph contexts"""
    graph1 = Graph()
    graph2 = Graph()

    with here.graph.bind(graph1):
        assert here.graph.get() == graph1
        with here.graph.bind(graph2):
            assert here.graph.get() == graph2
        assert here.graph.get() == graph1


def test_quote():
    """Test quoting triples in the current graph"""
    test_graph = Graph(base="https://example.com/")
    test_triple = (URIRef("s"), URIRef("p"), URIRef("o"))

    with here.graph.bind(test_graph):
        quoted = here.quote([test_triple])
        assert isinstance(quoted, QuotedGraph)
        assert test_triple in quoted


def test_langstr():
    """Test creating language-tagged literals"""
    test_graph = Graph(base="https://example.com/")

    with here.graph.bind(test_graph):
        lit = here.langstr("hello")
        assert lit.language == "en"
        assert str(lit) == "hello"
