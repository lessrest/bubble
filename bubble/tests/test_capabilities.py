import pytest
from pathlib import Path
from rdflib import Graph, URIRef, Literal, Namespace, BNode, RDF
from bubble import ShellCapability

# Test namespaces
SWA = Namespace("https://swa.sh/")
NT = Namespace("https://node.town/2024/")


@pytest.fixture
def graph():
    return Graph()


@pytest.fixture
def shell_capability():
    return ShellCapability()


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
