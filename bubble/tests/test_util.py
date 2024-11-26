import pytest
from rdflib import URIRef, Literal
from rdflib.namespace import RDF

from bubble.util import get_single_subject, print_n3, turtle


@pytest.fixture
def test_graph():
    """Create a test graph with a simple triple"""
    return turtle("""
        @prefix : <http://example.org/> .
        
        :subject a :TestType .
    """)


def test_print_n3(test_graph, capsys):
    """Test that print_n3 outputs formatted N3"""
    print_n3()
    
    captured = capsys.readouterr()
    
    # Verify output contains the triple components
    assert "http://example.org/subject" in captured.out
    assert "a" in captured.out  # RDF.type gets serialized as 'a' in N3
    assert "http://example.org/TestType" in captured.out


def test_get_single_subject(test_graph):
    """Test getting a single subject from a triple pattern"""
    # Test successful case
    result = get_single_subject(
        RDF.type, 
        URIRef("http://example.org/TestType")
    )
    assert result == URIRef("http://example.org/subject")

    # Test case with no matches
    with pytest.raises(ValueError, match="Expected 1 subject, got 0"):
        get_single_subject(RDF.type, Literal("nonexistent"))

    # Test case with multiple matches
    test_graph.add((
        URIRef("http://example.org/subject2"),
        RDF.type,
        URIRef("http://example.org/TestType")
    ))
    with pytest.raises(ValueError, match="Expected 1 subject, got 2"):
        get_single_subject(
            RDF.type,
            URIRef("http://example.org/TestType")
        )
