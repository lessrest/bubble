import pytest
import tempfile
from pathlib import Path
from rdflib import Graph, URIRef, Literal, Namespace
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
    # Create a simple echo command
    command = 'echo "test" > $out'
    invocation = URIRef("https://test.example/invocation")
    
    # Execute the command
    await shell_capability.execute(command, invocation, graph)
    
    # Verify results
    result_node = next(graph.objects(invocation, SWA.result))
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
    command = 'nonexistent-command'
    invocation = URIRef("https://test.example/invocation")
    
    with pytest.raises(Exception) as exc_info:
        await shell_capability.execute(command, invocation, graph)
    assert "Command failed" in str(exc_info.value)

async def test_art_generation_capability(art_capability, graph):
    """Test art generation capability setup"""
    parameter = URIRef("https://test.example/parameter")
    invocation = URIRef("https://test.example/invocation")
    
    # Add a prompt to the graph
    graph.add((parameter, NT.prompt, Literal("a test prompt")))
    
    # Mock replicate.async_run to avoid actual API calls
    import replicate
    original_run = replicate.async_run
    
    async def mock_run(*args, **kwargs):
        class MockResult:
            async def aread(self):
                return b"mock image data"
        return [MockResult()]
    
    replicate.async_run = mock_run
    
    try:
        await art_capability.execute(parameter, invocation, graph)
        
        # Verify results
        result_node = next(graph.objects(invocation, SWA.result))
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
        await art_capability.execute(parameter, invocation, graph)
    assert "No prompt found" in str(exc_info.value)
