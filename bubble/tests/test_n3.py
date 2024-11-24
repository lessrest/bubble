import pytest
from rdflib import Graph, URIRef, Literal, Namespace
from bubble import StepExecution, FileHandler, FileResult
from bubble.n3_utils import get_single_object, get_objects

# Test namespaces
SWA = Namespace("https://swa.sh/")
NT = Namespace("https://node.town/2024/")


@pytest.fixture
def basic_n3():
    """Creates basic N3 content for testing"""
    return """
@base <https://test.example/> .
@prefix nt: <https://node.town/2024/> .

<#> nt:precedes <next> .
<next> nt:supposes <supposition> .
"""


@pytest.fixture
def processor(basic_n3):
    """Creates a StepExecution instance with basic N3 content"""
    graph = Graph(base="https://test.example/")
    graph.parse(data=basic_n3, format="n3")
    processor = StepExecution(base="https://test.example/", step=None)
    processor.graph = graph
    return processor


def test_get_next_step(processor):
    """Test getting the next step from a graph"""
    step = URIRef("https://test.example/#")
    next_step = processor.get_next_step(step)
    assert next_step == URIRef("https://test.example/next")


def test_get_supposition(processor):
    """Test getting the supposition for a step"""
    next_step = URIRef("https://test.example/next")
    supposition = processor.get_supposition(next_step)
    assert supposition == URIRef("https://test.example/supposition")


def test_get_single_object(processor):
    """Test get_single_object utility function"""
    step = URIRef("https://test.example/#")
    next_step = get_single_object(processor.graph, step, NT.precedes)
    assert next_step == URIRef("https://test.example/next")


def test_get_objects(processor):
    """Test get_objects utility function"""
    step = URIRef("https://test.example/#")
    objects = get_objects(processor.graph, step, NT.precedes)
    assert len(objects) == 1
    assert objects[0] == URIRef("https://test.example/next")


async def test_file_handler_metadata(tmp_path):
    """Test FileHandler metadata collection"""
    import trio

    test_file = tmp_path / "test.txt"
    async with await trio.open_file(str(test_file), "w") as f:
        await f.write("test content")

    result = await FileHandler.get_file_metadata(str(test_file))

    assert isinstance(result, FileResult)
    assert result.path == str(test_file)
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
