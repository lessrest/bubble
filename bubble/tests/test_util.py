import pytest
from rdflib import Graph, URIRef, Literal
from rdflib.namespace import RDF

from bubble.vars import using_graph
from bubble.util import get_single_subject

def test_get_single_subject():
    with using_graph(Graph()) as g:
        # Add a test triple
        subject = URIRef("http://example.org/subject")
        predicate = RDF.type
        object = URIRef("http://example.org/TestType")
        g.add((subject, predicate, object))
        
        # Test successful case
        result = get_single_subject(predicate, object)
        assert result == subject

        # Test case with no matches
        with pytest.raises(ValueError, match="Expected 1 subject, got 0"):
            get_single_subject(predicate, Literal("nonexistent"))
            
        # Test case with multiple matches
        subject2 = URIRef("http://example.org/subject2")
        g.add((subject2, predicate, object))
        with pytest.raises(ValueError, match="Expected 1 subject, got 2"):
            get_single_subject(predicate, object)
