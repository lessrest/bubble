from rdflib import Graph, Literal, URIRef
from bubble.vars import using_graph, graphvar, langstr, bind_prefixes, quote
from bubble.prfx import AS, NT, SWA


def test_using_graph():
    """Test that using_graph properly manages graph context"""
    original_graph = graphvar.get()
    test_graph = Graph()

    # Test context management
    with using_graph(test_graph) as g:
        assert graphvar.get() is test_graph
        assert g is test_graph

    # Verify original graph is restored
    assert graphvar.get() is original_graph


def test_nested_using_graph():
    """Test nested graph contexts work correctly"""
    graph1 = Graph()
    graph2 = Graph()

    with using_graph(graph1):
        assert graphvar.get() is graph1
        with using_graph(graph2):
            assert graphvar.get() is graph2
        assert graphvar.get() is graph1


def test_langstr():
    """Test language string literal creation"""
    text = "Hello World"
    lit = langstr(text)
    assert isinstance(lit, Literal)
    assert lit.value == text
    assert lit.language == "en"


def test_bind_prefixes():
    """Test prefix binding"""
    test_graph = Graph()
    with using_graph(test_graph):
        bind_prefixes()

        # Check that expected prefixes are bound
        assert (
            test_graph.namespace_manager.compute_qname(str(SWA))[0]
            == "swa"
        )
        assert (
            test_graph.namespace_manager.compute_qname(str(NT))[0]
            == "nt"
        )
        assert (
            test_graph.namespace_manager.compute_qname(str(AS))[0]
            == "as"
        )


def test_quote():
    """Test creation of quoted graphs"""
    test_graph = Graph()
    with using_graph(test_graph):
        # Create some test triples
        subject = URIRef("http://example.org/subject")
        predicate = URIRef("http://example.org/predicate")
        object = URIRef("http://example.org/object")
        triples = [(subject, predicate, object)]
        
        # Create quoted graph
        quoted = quote(triples)
        
        # Verify it's a QuotedGraph
        assert quoted.__class__.__name__ == "QuotedGraph"
        
        # Verify the triple was added
        assert (subject, predicate, object) in quoted
        
        # Verify it has a unique identifier
        assert quoted.identifier is not None
