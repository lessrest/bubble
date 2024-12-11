import pytest
from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, RDFS
from swash.rdfa import autoexpanding, rdf_resource
from swash.html import document, Fragment, root

EX = Namespace("http://example.org/")

def test_rdfa_roundtrip():
    # Create a simple test graph
    g = Graph()
    subject = EX.subject
    g.add((subject, RDF.type, EX.TestType))
    g.add((subject, RDFS.label, Literal("Test Label")))
    g.add((subject, EX.property, Literal("Test Value")))
    
    # Render the graph to HTML with RDFa
    with document():
        with autoexpanding(4):
            rdf_resource(subject, {
                "type": EX.TestType,
                "predicates": [
                    (RDFS.label, Literal("Test Label")),
                    (EX.property, Literal("Test Value"))
                ]
            })
    
    # Get the rendered HTML
    doc = root.get()
    assert isinstance(doc, Fragment)
    html = doc.to_html()
    
    # Parse the HTML back to a graph
    parsed = Graph()
    parsed.parse(data=html, format="rdfa")
    
    # Check for isomorphism
    assert g.isomorphic(parsed), "Parsed RDFa should match original graph"
