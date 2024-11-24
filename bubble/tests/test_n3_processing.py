import pytest
from pathlib import Path
from rdflib import URIRef, Namespace
from rich import inspect
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
@prefix eye: <http://eulersharp.sourceforge.net/2003/03swap/log-rules#> .
@prefix log: <http://www.w3.org/2000/10/swap/log#> .
@prefix math: <http://www.w3.org/2000/10/swap/math#> .
@prefix nt: <https://node.town/2024/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix swa: <https://swa.sh/> .
@base <https://test.example/> .

#
nt:owns owl:inverseOf nt:isOwnedBy .
nt:succeeds owl:inverseOf nt:precedes .
nt:isPartOf owl:inverseOf nt:hasPart .
owl:inverseOf owl:inverseOf owl:inverseOf .

#
{
   ?p owl:inverseOf ?q .
   ?a ?p ?b
}
=>
{
   ?b ?q ?a
} .

#
{
   <#> nt:supposes ?g
}
=> ?g .

#
_:next a nt:Step ;
   nt:succeeds <#> .


# next = current + decisions - revocations
{
   ?s1 a nt:Step .
   ?s2 nt:succeeds ?s1 .
   [] eye:findall (
       ?g1
       {
           ?s1 nt:supposes ?g1
       }
       ?gs1
   ) ;
       eye:findall (
           ?g2
           {
               ?s1 nt:decides ?g2
           }
           ?gs2
       ) ;
       eye:findall (
           ?g3
           {
               ?s1 nt:revokes ?g3
           }
           ?gs3
       ) .
   ?gs1 log:conjunction ?g1m .
   ?gs2 log:conjunction ?g2m .
   ?gs3 log:conjunction ?g3m .
   ( ?g1m ?g3m ) eye:graphDifference ?tmp .
   ( ?tmp ?g2m ) log:conjunction ?result .
}
=>
{
   ?s2 nt:supposes ?result
} .


#
{
   nt:nonce nt:ranks ?rank .
   ( ?rank 1 ) math:sum ?next
}
=>
{
   <#> nt:decides
   {
       nt:nonce nt:ranks ?next
   } .
   <#> nt:revokes
   {
       nt:nonce nt:ranks ?rank
   } .
} .

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
    # Create a temporary file with N3 content
    n3_file = tmp_path / "test.n3"
    n3_file.write_text(basic_n3)

    # Process and reason over the N3 file
    await processor.reason(n3_file)
    processor.print_n3()

    # Verify basic graph structure
    step = URIRef("https://test.example/#")
    next_step = processor.get_next_step(step)
    inspect(next_step)
    supposition = processor.get_supposition(next_step)
    print(supposition)

    # Process invocations
    await processor.process_invocations(step)

    # Verify results
    invocations = list(processor.graph.objects(step, NT.invokes))
    assert len(invocations) == 1

    processor.print_n3()
    inspect(invocations[0])

    # Check if result was added to graph
    result = next(processor.graph.objects(invocations[0], NT.result), None)
    assert result is not None

    # Verify file was created
    path = next(processor.graph.objects(result, NT.path))
    assert Path(path).exists()
    with open(path) as f:
        content = f.read().strip()
        assert content == "test"
