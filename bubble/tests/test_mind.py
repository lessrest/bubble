import pytest
import trio
from pathlib import Path
from rdflib import Graph, URIRef, Literal
from rdflib.namespace import RDF, RDFS

from bubble.mind import reason

# Test data directory
TEST_DIR = Path(__file__).parent / "test_data"
TEST_DIR.mkdir(exist_ok=True)

def create_test_files():
    """Create temporary N3 files for testing"""
    
    # Basic facts
    facts = """
    @prefix : <http://example.org/> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    
    :Socrates a :Human .
    :Human rdfs:subClassOf :Mortal .
    """.strip()
    
    # Simple rule
    rules = """
    @prefix : <http://example.org/> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    @prefix log: <http://www.w3.org/2000/10/swap/log#> .
    
    {?A rdfs:subClassOf ?B . ?X a ?A} => {?X a ?B} .
    """.strip()
    
    facts_file = TEST_DIR / "facts.n3"
    rules_file = TEST_DIR / "rules.n3"
    
    facts_file.write_text(facts)
    rules_file.write_text(rules)
    
    return [str(facts_file), str(rules_file)]

@pytest.fixture
async def test_files():
    """Fixture to create and cleanup test files"""
    files = create_test_files()
    yield files
    # Cleanup
    for file in files:
        Path(file).unlink()
    TEST_DIR.rmdir()

@pytest.mark.trio
async def test_basic_reasoning(test_files):
    """Test that basic reasoning works with EYE"""
    result = await reason(test_files)
    
    # Check that Socrates is inferred to be Mortal
    socrates = URIRef("http://example.org/Socrates")
    mortal = URIRef("http://example.org/Mortal")
    
    assert (socrates, RDF.type, mortal) in result, "Failed to infer Socrates is Mortal"

@pytest.mark.trio
async def test_empty_input():
    """Test handling of empty input"""
    with pytest.raises(Exception):
        await reason([])

@pytest.mark.trio
async def test_invalid_file():
    """Test handling of invalid file path"""
    with pytest.raises(Exception):
        await reason(["nonexistent.n3"])
