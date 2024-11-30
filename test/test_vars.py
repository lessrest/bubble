from rdflib import Graph, URIRef
from rdflib.graph import QuotedGraph
from bubble import vars


def test_graph_context():
    """Test that binding properly manages graph context"""
    test_graph = Graph()
    test_graph.add((URIRef("s"), URIRef("p"), URIRef("o")))
    assert vars.graph.get() != test_graph

    with vars.graph.bind(test_graph) as g:
        assert g == test_graph
        assert vars.graph.get() == test_graph

    assert vars.graph.get() != test_graph


def test_nested_graph_context():
    """Test nested graph contexts"""
    graph1 = Graph()
    graph2 = Graph()

    with vars.graph.bind(graph1):
        assert vars.graph.get() == graph1
        with vars.graph.bind(graph2):
            assert vars.graph.get() == graph2
        assert vars.graph.get() == graph1


def test_quote():
    """Test quoting triples in the current graph"""
    test_graph = Graph()
    test_triple = (URIRef("s"), URIRef("p"), URIRef("o"))

    with vars.graph.bind(test_graph):
        quoted = vars.quote([test_triple])
        assert isinstance(quoted, QuotedGraph)
        assert test_triple in quoted


def test_langstr():
    """Test creating language-tagged literals"""
    test_graph = Graph()

    with vars.graph.bind(test_graph):
        lit = vars.langstr("hello")
        assert lit.language == "en"
        assert str(lit) == "hello"
