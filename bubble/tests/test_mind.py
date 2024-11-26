"""Tests for the EYE reasoner integration.

These tests verify that:
1. Basic N3 reasoning works with simple rules and facts
2. Error cases are handled properly
3. The reasoner can process standard N3 inference patterns
"""

from pathlib import Path
import pytest
from rdflib import URIRef, Namespace, Graph
from rdflib.namespace import RDF, RDFS

from bubble.mind import reason


@pytest.fixture
def test_data():
    """Test data for N3 reasoning"""
    EX = Namespace("http://example.org/")
    
    return {
        "facts": f"""
        @prefix : <{EX}> .
        @prefix rdfs: <{RDFS}> .
        
        :Socrates a :Human .
        :Human rdfs:subClassOf :Mortal .
        """.strip(),
        
        "rules": f"""
        @prefix : <{EX}> .
        @prefix rdfs: <{RDFS}> .
        @prefix log: <http://www.w3.org/2000/10/swap/log#> .
        
        {{?A rdfs:subClassOf ?B . ?X a ?A}} => {{?X a ?B}} .
        """.strip()
    }

@pytest.fixture
async def test_files(tmp_path, test_data):
    """Fixture providing temporary N3 test files"""
    facts_file = tmp_path / "facts.n3" 
    rules_file = tmp_path / "rules.n3"
    
    facts_file.write_text(test_data["facts"])
    rules_file.write_text(test_data["rules"])
    
    return [str(facts_file), str(rules_file)]

@pytest.mark.trio
async def test_basic_reasoning(test_files):
    """Verify that basic RDFS reasoning works.
    
    Tests that the reasoner can infer Socrates is Mortal
    using RDFS subclass reasoning.
    """
    result = await reason(test_files)
    
    # Verify inference
    socrates = URIRef("http://example.org/Socrates")
    mortal = URIRef("http://example.org/Mortal")
    
    assert (socrates, RDF.type, mortal) in result, \
        "Failed to infer that Socrates is Mortal"

@pytest.mark.trio
async def test_empty_input():
    """Verify that empty input is handled properly."""
    with pytest.raises(ValueError, match="No input files provided"):
        await reason([])

@pytest.mark.trio
async def test_invalid_file():
    """Verify that invalid file paths are handled properly."""
    with pytest.raises(FileNotFoundError):
        await reason(["nonexistent.n3"])
