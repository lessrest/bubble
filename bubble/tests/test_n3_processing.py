import pytest
import tempfile
from pathlib import Path
from rdflib import Graph, URIRef, Literal, Namespace
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
@prefix eye: <http://eulersharp.sourceforge.net/2003/03swap/eye#> .
@prefix log: <http://www.w3.org/2000/10/swap/log#> .
@prefix math: <http://www.w3.org/2000/10/swap/math#> .
@prefix nt: <https://node.town/2024/#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix swa: <https://swa.sh/> .
@base <https://test.example/> .

# Core axioms
swa:succeeds owl:inverseOf swa:precedes .

# Step succession rule
{
   ?s1 a swa:Step .
   ?s2 swa:succeeds ?s1 .
   [] eye:findall (
       ?g1
       {
           ?s1 swa:supposes ?g1 
       }
       ?gs1
   ) .
   ?gs1 log:conjunction ?g1m .
}
=> 
{
   ?s2 swa:supposes ?g1m 
} .

# Test step
<#> a swa:Step ;
    swa:invokes [
        a nt:Invocation ;
        nt:invokes [ a nt:ShellCapability ] ;
        nt:provides [
            a nt:ShellCommand ;
            nt:value "echo 'test' > $out"
        ]
    ] ;
    swa:precedes _:next .

_:next a swa:Step ;
    swa:supposes {
        swa:nonce swa:ranks 1 .
    } .
"""


async def test_n3_processing_basic(processor, basic_n3, tmp_path):
    """Test basic N3 processing with a shell command"""
    # Create a temporary file with N3 content
    n3_file = tmp_path / "test.n3"
    n3_file.write_text(basic_n3)

    # Process and reason over the N3 file
    await processor.reason(n3_file)

    # Verify basic graph structure
    step = URIRef("https://test.example/#")
    next_step = processor.get_next_step(step)
    assert next_step is not None

    supposition = processor.get_supposition(next_step)
    assert supposition is not None

    # Process invocations
    await processor.process_invocations(step)

    # Verify results
    invocations = list(processor.graph.objects(step, SWA.invokes))
    assert len(invocations) == 1

    # Check if result was added to graph
    result = next(processor.graph.objects(invocations[0], SWA.result), None)
    assert result is not None

    # Verify file was created
    path = next(processor.graph.objects(result, NT.path))
    assert Path(path).exists()
    with open(path) as f:
        content = f.read().strip()
        assert content == "test"


async def test_n3_processing_no_next_step(processor):
    """Test handling of missing next step"""
    n3_content = """
@prefix swa: <https://swa.sh/> .
@base <https://test.example/> .

<#> a swa:Step .
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".n3") as f:
        f.write(n3_content)
        f.flush()
        processor.graph.parse(f.name, format="n3")

        with pytest.raises(ValueError) as exc_info:
            await processor.process(n3_content)
        assert "No next step found" in str(exc_info.value)


async def test_n3_processing_no_supposition(processor):
    """Test handling of missing supposition"""
    n3_content = """
@prefix swa: <https://swa.sh/> .
@base <https://test.example/> .

<#> a swa:Step ;
    swa:precedes <#next> .

<#next> a swa:Step .
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".n3") as f:
        f.write(n3_content)
        f.flush()
        processor.graph.parse(f.name, format="n3")

        with pytest.raises(ValueError) as exc_info:
            await processor.process(n3_content)
        assert "No supposition found" in str(exc_info.value)
