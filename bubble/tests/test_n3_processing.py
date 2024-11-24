import pytest
from pathlib import Path
from rdflib import URIRef, Namespace
from bubble import N3Processor

# Test namespaces
SWA = Namespace("https://swa.sh/")
NT = Namespace("https://node.town/2024/")


@pytest.fixture
def processor():
    return N3Processor(base="https://test.example/")


@pytest.fixture
def basic_n3():
    return """
@prefix : <#> .
@prefix nt: <https://node.town/2024/> .
@base <https://test.example/> .

# Test step
<#> a nt:Step ;
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
"""


async def test_n3_processing_basic(processor, basic_n3, tmp_path):
    """Test basic N3 processing with a shell command"""
    rules_file = Path(__file__).parent.parent / "rules" / "core.n3"
    # Create a temporary file with N3 content
    n3_file = tmp_path / "test.n3"
    n3_file.write_text(basic_n3)

    # Process and reason over the N3 file
    await processor.reason([rules_file, n3_file])

    # Verify basic graph structure
    step = URIRef("https://test.example/#")

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
