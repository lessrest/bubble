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

# Test data directory in the same folder as this test file
TEST_DIR = Path(__file__).parent / "test_data"

def setup_test_files():
    """Create temporary N3 files with test data.
    
    Returns:
        list[str]: Paths to the created N3 files
    """
    # Ensure test directory exists
    TEST_DIR.mkdir(exist_ok=True)
    
    # Define test namespaces
    EX = Namespace("http://example.org/")
    
    # Basic facts about Socrates
    facts = f"""
    @prefix : <{EX}> .
    @prefix rdfs: <{RDFS}> .
    
    :Socrates a :Human .
    :Human rdfs:subClassOf :Mortal .
    """.strip()
    
    # RDFS subclass inference rule
    rules = f"""
    @prefix : <{EX}> .
    @prefix rdfs: <{RDFS}> .
    @prefix log: <http://www.w3.org/2000/10/swap/log#> .
    
    {{?A rdfs:subClassOf ?B . ?X a ?A}} => {{?X a ?B}} .
    """.strip()
    
    # Write files
    facts_file = TEST_DIR / "facts.n3"
    rules_file = TEST_DIR / "rules.n3"
    
    facts_file.write_text(facts)
    rules_file.write_text(rules)
    
    return [str(facts_file), str(rules_file)]

@pytest.fixture
async def test_files():
    """Fixture providing test N3 files and cleanup.
    
    Yields:
        list[str]: Paths to the test N3 files
    """
    files = setup_test_files()
    yield files
    # Cleanup after tests
    for file in files:
        Path(file).unlink(missing_ok=True)
    TEST_DIR.rmdir()

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
