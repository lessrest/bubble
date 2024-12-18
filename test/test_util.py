import pytest

from rdflib import URIRef, Literal
from rdflib.namespace import RDF

from swash import here
from swash.util import turtle, print_n3, get_single_subject


@pytest.fixture
def test_graph():
    """Create a test graph with a simple triple"""
    with here.graph.bind(
        turtle("""
        @prefix : <http://example.org/> .

        :subject a :TestType .
    """)
    ) as g:
        yield g


def test_print_n3(test_graph, capsys):
    """Test that print_n3 outputs formatted N3"""
    print_n3(test_graph)

    captured = capsys.readouterr()
    assert captured.out.find(":subject") > -1


def test_get_single_subject(test_graph):
    """Test getting a single subject from a triple pattern"""
    # Test successful case
    result = get_single_subject(
        RDF.type,
        URIRef("http://example.org/TestType"),
    )
    assert result == URIRef("http://example.org/subject")

    # Test case with no matches
    with pytest.raises(ValueError, match="Expected 1 subject, got 0"):
        get_single_subject(RDF.type, Literal("nonexistent"))

    # Test case with multiple matches
    test_graph.add(
        (
            URIRef("http://example.org/subject2"),
            RDF.type,
            URIRef("http://example.org/TestType"),
        )
    )
    with pytest.raises(ValueError, match="Expected 1 subject, got 2"):
        get_single_subject(RDF.type, URIRef("http://example.org/TestType"))
