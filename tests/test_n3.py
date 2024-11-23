import pytest
from rdflib import Graph, URIRef, Literal, Namespace
from n3 import N3Processor, FileHandler, FileResult

# Test namespaces
SWA = Namespace("https://swa.sh/")
NT = Namespace("https://node.town/2024/")

@pytest.fixture
def processor():
    return N3Processor(base="https://test.example/")

@pytest.fixture
def basic_graph():
    """Creates a basic graph with a single step"""
    graph = Graph(base="https://test.example/")
    step = URIRef("https://test.example/#")
    next_step = URIRef("https://test.example/next")
    
    graph.add((step, SWA.precedes, next_step))
    graph.add((next_step, SWA.supposes, URIRef("https://test.example/supposition")))
    
    return graph

def test_processor_initialization(processor):
    """Test basic processor initialization"""
    assert processor.base == "https://test.example/"
    assert isinstance(processor.graph, Graph)
    assert isinstance(processor.file_handler, FileHandler)

def test_get_next_step(processor, basic_graph):
    """Test getting the next step from a graph"""
    processor.graph = basic_graph
    step = URIRef("https://test.example/#")
    next_step = processor.get_next_step(step)
    
    assert next_step == URIRef("https://test.example/next")

def test_get_supposition(processor, basic_graph):
    """Test getting the supposition for a step"""
    processor.graph = basic_graph
    next_step = URIRef("https://test.example/next")
    supposition = processor.get_supposition(next_step)
    
    assert supposition == URIRef("https://test.example/supposition")

@pytest.mark.trio
async def test_file_handler_metadata():
    """Test FileHandler metadata collection"""
    import tempfile
    import trio
    
    # Create a temporary file with some content
    async with await trio.open_file(tempfile.mktemp(), 'w') as f:
        await f.write("test content")
        path = f.name
    
    result = await FileHandler.get_file_metadata(path)
    
    assert isinstance(result, FileResult)
    assert result.path == path
    assert result.size > 0
    assert result.content_hash is not None
    assert result.creation_date is not None

@pytest.mark.trio
async def test_create_result_node():
    """Test creating a result node in the graph"""
    graph = Graph()
    file_result = FileResult(
        path="/test/path",
        size=100,
        content_hash="abc123"
    )
    
    result_node = await FileHandler.create_result_node(graph, file_result)
    
    assert (result_node, NT.path, Literal("/test/path")) in graph
    assert (result_node, NT.size, Literal(100)) in graph
    assert (result_node, NT.contentHash, Literal("abc123")) in graph
