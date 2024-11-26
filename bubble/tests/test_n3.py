from typing import LiteralString
from pathlib import Path

import pytest

from rdflib import BNode, Graph, URIRef, Namespace

from bubble.n3 import StepExecution

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

:surface a nt:Surface ; nt:head :step .
 :step a nt:Step ;
    nt:supposes {
        :surface nt:head :step
    } ;
    nt:invokes [
        a nt:Invocation ;
        nt:invokes [ a nt:ShellCapability ] ;
        nt:provides [
            a nt:ShellCommand ;
            nt:value "echo 'test' > $out"
        ]
    ] .

:next a nt:Step ;
    nt:succeeds :step .
"""


@pytest.fixture
def processor(basic_n3: LiteralString):
    """Creates a StepExecution instance with basic N3 content"""
    graph = Graph(base="https://test.example/")
    graph.parse(data=basic_n3, format="n3")
    processor = StepExecution(base="https://test.example/", step=None)
    processor.graph = graph
    return processor


@pytest.fixture
async def shell_processor(shell_command_n3: LiteralString, tmp_path: Path):
    """Creates a StepExecution instance with shell command N3"""
    n3_file = tmp_path / "test.n3"
    n3_file.write_text(shell_command_n3)
    execution = StepExecution(base="https://test.example/", step=str(n3_file))
    await execution.reason()
    return execution


async def test_process_shell_command(shell_processor: StepExecution):
    """Test processing a shell command invocation"""
    step = URIRef("https://test.example/#step")

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


async def test_process_invalid_invocation(processor: StepExecution):
    """Test handling invalid invocation"""
    step = URIRef("https://test.example/#")

    # Add invalid invocation
    invocation = BNode()
    processor.graph.add((step, NT.invokes, invocation))
    processor.graph.add((invocation, NT.invokes, BNode()))

    # Process should complete without error, skipping invalid invocation
    await processor.process_invocations(step)

    # Verify no results were added for invalid invocation
    results = list(processor.graph.objects(invocation, NT.result))
    assert len(results) == 0
