"""Tests for the EYE reasoner integration.

These tests verify that:
1. Basic N3 reasoning works with simple rules and facts
2. Error cases are handled properly
3. The reasoner can process standard N3 inference patterns
"""

import pytest
from rdflib import URIRef, Namespace, Graph
from rdflib.namespace import RDF, RDFS

from bubble.mind import reason


@pytest.fixture
def test_graphs():
    """Test graphs for N3 reasoning"""
    EX = Namespace("http://example.org/")
    
    # Create facts graph
    facts = Graph()
    facts.bind('', EX)
    facts.bind('rdfs', RDFS)
    
    facts.add((EX.Socrates, RDF.type, EX.Human))
    facts.add((EX.Human, RDFS.subClassOf, EX.Mortal))
    
    # Create rules graph
    rules = Graph()
    rules.bind('', EX)
    rules.bind('rdfs', RDFS)
    rules.parse(data="""
        @prefix : <http://example.org/> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix log: <http://www.w3.org/2000/10/swap/log#> .
        
        {?A rdfs:subClassOf ?B . ?X a ?A} => {?X a ?B} .
    """, format='n3')
    
    return [facts, rules]


@pytest.mark.trio
async def test_basic_reasoning(test_graphs):
    """Verify that basic RDFS reasoning works.
    
    Tests that the reasoner can infer Socrates is Mortal
    using RDFS subclass reasoning.
    """
    result = await reason(test_graphs)
    
    # Verify inference
    socrates = URIRef("http://example.org/Socrates")
    mortal = URIRef("http://example.org/Mortal")
    
    assert (socrates, RDF.type, mortal) in result, \
        "Failed to infer that Socrates is Mortal"


@pytest.mark.trio
async def test_empty_input():
    """Verify that empty input is handled properly."""
    with pytest.raises(ValueError, match="No input graphs provided"):
        await reason([])
