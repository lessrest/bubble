import tempfile
import pytest
from pathlib import Path
from rdflib import Graph, URIRef, Literal, Namespace, BNode
from bubble import StepExecution, FileHandler, FileResult
from bubble.n3_utils import get_single_object, get_objects

# Test namespaces
SWA = Namespace("https://swa.sh/")
NT = Namespace("https://node.town/2024/")


# Core fixtures
@pytest.fixture
def basic_n3():
    """Creates basic N3 content for testing graph traversal"""
    return """
@base <https://test.example/> .
@prefix nt: <https://node.town/2024/> .

<#> nt:precedes <next> .
<next> nt:supposes <supposition> .
"""

@pytest.fixture
def shell_command_n3():
    """Creates N3 content for testing shell command invocation"""
    return """
@base <https://test.example/> .
@prefix : <#> .
@prefix nt: <https://node.town/2024/> .

nt:nonce nt:ranks 1 .

<#> a nt:Step ;
    nt:ranks 1 ;
    nt:supposes {
        nt:nonce nt:ranks 1
    } ;
    nt:invokes [
        a nt:Invocation ;
        nt:invokes [ a nt:ShellCapability ] ;
        nt:provides [
            a nt:ShellCommand ;
            nt:value "echo 'test' > $out"
        ]
    ] .

<#next> a nt:Step ;
    nt:succeeds <#> .
"""

@pytest.fixture
def processor(basic_n3):
    """Creates a StepExecution instance with basic N3 content"""
    graph = Graph(base="https://test.example/")
    graph.parse(data=basic_n3, format="n3")
    processor = StepExecution(base="https://test.example/", step=None)
    processor.graph = graph
    return processor

@pytest.fixture
def shell_processor(shell_command_n3, tmp_path):
    """Creates a StepExecution instance with shell command N3"""
    n3_file = tmp_path / "test.n3"
    n3_file.write_text(shell_command_n3)
    return StepExecution(base="https://test.example/", step=str(n3_file))


# Core N3 processing tests
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


# File handling tests
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


# Invocation processing tests
async def test_process_shell_command(shell_processor):
    """Test processing a shell command invocation"""
    step = URIRef("https://test.example/#")
    
    # Process invocations
    await shell_processor.process_invocations(step)

    # Verify invocation results
    invocations = list(shell_processor.graph.objects(step, NT.invokes))
    assert len(invocations) == 1

    # Check result was added
    result = next(shell_processor.graph.objects(invocations[0], NT.result))
    assert result is not None

    # Verify file was created with expected content
    path = next(shell_processor.graph.objects(result, NT.path))
    assert Path(path).exists()
    with open(path) as f:
        content = f.read().strip()
        assert content == "test"

async def test_process_invalid_invocation(processor):
    """Test handling invalid invocation"""
    step = URIRef("https://test.example/#")
    
    # Add invalid invocation
    invocation = BNode()
    processor.graph.add((step, NT.invokes, invocation))
    processor.graph.add((invocation, NT.invokes, BNode()))

    # Process should complete without error
    await processor.process_invocations(step)
