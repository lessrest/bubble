import pytest
from pathlib import Path
from rdflib import Graph, URIRef, Literal, Namespace, BNode, RDF
from bubble import ShellCapability, ArtGenerationCapability

# Test namespaces
SWA = Namespace("https://swa.sh/")
NT = Namespace("https://node.town/2024/")


@pytest.fixture
def graph():
    return Graph()


@pytest.fixture
def shell_capability():
    return ShellCapability()


@pytest.fixture
def art_capability():
    return ArtGenerationCapability()


async def test_shell_capability_success(shell_capability, graph):
    """Test successful shell command execution"""
    # Create invocation with command
    invocation = URIRef("https://test.example/invocation")
    command_node = BNode()

    graph.add((invocation, RDF.type, NT.Invocation))
    graph.add((invocation, NT.provides, command_node))
    graph.add((command_node, RDF.type, NT.ShellCommand))
    graph.add((command_node, NT.value, Literal('echo "test" > $out')))

    # Execute the command
    await shell_capability.execute(graph, invocation, None, [command_node])

    # Verify results
    result_node = next(graph.objects(invocation, NT.result))
    assert result_node is not None

    # Check file path exists
    path = next(graph.objects(result_node, NT.path))
    assert Path(path).exists()

    # Verify content
    with open(path) as f:
        content = f.read().strip()
        assert content == "test"


async def test_shell_capability_failure(shell_capability, graph):
    """Test shell command failure handling"""
    invocation = URIRef("https://test.example/invocation")
    graph.add((invocation, RDF.type, NT.Invocation))

    with pytest.raises(ValueError) as exc_info:
        await shell_capability.execute(graph, invocation, None, [])
    assert "No shell command provided" in str(exc_info.value)


async def test_art_generation_capability(art_capability, graph):
    """Test art generation capability setup"""
    parameter = URIRef("https://test.example/parameter")
    invocation = URIRef("https://test.example/invocation")

    # Add a prompt to the graph
    graph.add((parameter, RDF.type, NT.ImagePrompt))
    graph.add((parameter, NT.prompt, Literal("a test prompt")))

    # Mock replicate.async_run to avoid actual API calls
    import replicate

    original_run = replicate.async_run

    # async def mock_run(*args, **kwargs):
    #     class MockResult:
    #         async def aread(self):
    #             return b"mock image data"

    #     return MockResult()

    # replicate.async_run = mock_run

    try:
        await art_capability.execute(graph, invocation, None, [parameter])

        # Verify results
        result_node = next(graph.objects(invocation, NT.result))
        assert result_node is not None

        # Check file path exists and ends with .webp
        path = str(next(graph.objects(result_node, NT.path)))
        assert path.endswith(".webp")
        assert Path(path).exists()

    finally:
        # Restore original function
        replicate.async_run = original_run


async def test_art_generation_no_prompt(art_capability, graph):
    """Test art generation fails without prompt"""
    parameter = URIRef("https://test.example/parameter")
    invocation = URIRef("https://test.example/invocation")

    with pytest.raises(ValueError) as exc_info:
        await art_capability.execute(graph, invocation, None, [parameter])
    assert "No prompt found" in str(exc_info.value)


async def test_shell_capability_with_stdin(shell_capability, graph):
    """Test shell command with standard input"""
    invocation = URIRef("https://test.example/invocation")
    command_node = BNode()
    stdin_node = BNode()

    graph.add((invocation, RDF.type, NT.Invocation))
    graph.add((invocation, NT.provides, command_node))
    graph.add((invocation, NT.provides, stdin_node))
    graph.add((command_node, RDF.type, NT.ShellCommand))
    graph.add((command_node, NT.value, Literal("cat > $out")))
    graph.add((stdin_node, RDF.type, NT.StandardInput))
    graph.add((stdin_node, NT.value, Literal("test input")))

    await shell_capability.execute(
        graph, invocation, None, [command_node, stdin_node]
    )

    # Verify results
    result_node = next(graph.objects(invocation, NT.result))
    assert result_node is not None

    # Check file path exists
    path = next(graph.objects(result_node, NT.path))
    assert Path(path).exists()

    # Verify content
    with open(path) as f:
        content = f.read().strip()
        assert content == "test input"
