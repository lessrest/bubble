import pytest
from rdflib import Graph, URIRef, Literal, Namespace
from bubble import N3Processor, FileHandler, FileResult
from bubble.n3_utils import get_single_object, get_objects, show, reason, skolemize

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

    graph.add((step, NT.precedes, next_step))
    graph.add((next_step, NT.supposes, URIRef("https://test.example/supposition")))

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


def test_get_single_object(basic_graph):
    """Test get_single_object utility function"""
    step = URIRef("https://test.example/#")
    next_step = get_single_object(basic_graph, step, NT.precedes)
    assert next_step == URIRef("https://test.example/next")


def test_get_objects(basic_graph):
    """Test get_objects utility function"""
    step = URIRef("https://test.example/#")
    objects = get_objects(basic_graph, step, NT.precedes)
    assert len(objects) == 1
    assert objects[0] == URIRef("https://test.example/next")


async def test_file_handler_metadata():
    """Test FileHandler metadata collection"""
    import tempfile
    import trio

    async with await trio.open_file(tempfile.mktemp(), "w") as f:
        await f.write("test content")
        path = f.name

    result = await FileHandler.get_file_metadata(path)

    assert isinstance(result, FileResult)
    assert result.path == path
    assert result.size is not None
    assert result.content_hash is not None
    assert result.creation_date is not None


async def test_create_result_node():
    """Test creating a result node in the graph"""
    graph = Graph()
    file_result = FileResult(path="/test/path", size=100, content_hash="abc123")

    result_node = await FileHandler.create_result_node(graph, file_result)

    assert (result_node, NT.path, Literal("/test/path")) in graph
    assert (result_node, NT.size, Literal(100)) in graph
    assert (result_node, NT.contentHash, Literal("abc123")) in graph
