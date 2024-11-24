import tempfile
import pytest
from pathlib import Path
from rdflib import URIRef, Namespace
from bubble import StepExecution
from bubble.n3_utils import print_n3

# Test namespaces
SWA = Namespace("https://swa.sh/")
NT = Namespace("https://node.town/2024/")


@pytest.fixture
def basic_n3():
    return """
@base <https://test.example/> .
@prefix : <#> .
@prefix nt: <https://node.town/2024/> .

nt:nonce nt:ranks 1 .

# Test step
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


async def test_n3_processing_basic(basic_n3, tmp_path):
    """Test basic N3 processing with a shell command"""
    # Create a temporary file with N3 content
    n3_file = tmp_path / "test.n3"
    n3_file.write_text(basic_n3)

    # Process and reason over the N3 file
    graph_file_tmp = Path(tempfile.mktemp())
    graph_file_tmp.write_text(basic_n3)
    processor = StepExecution(
        base="https://test.example/", step=graph_file_tmp.as_posix()
    )
    await processor.reason()

    # Verify basic graph structure
    step = URIRef("https://test.example/#")

    # Print the graph
    print_n3(processor.graph)

    next_step = processor.get_next_step(step)
    supposition = processor.get_supposition(next_step)

    assert supposition is not None

    # Process invocations
    await processor.process_invocations(step)

    # Verify results
    invocations = list(processor.graph.objects(step, NT.invokes))
    assert len(invocations) == 1

    # Check if result was added to graph
    result = next(processor.graph.objects(invocations[0], NT.result), None)
    assert result is not None

    # Verify file was created
    path = next(processor.graph.objects(result, NT.path))
    assert Path(path).exists()
    with open(path) as f:
        content = f.read().strip()
        assert content == "test"
