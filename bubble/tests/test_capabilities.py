from pathlib import Path

import httpx
import pytest

from rdflib import Graph, URIRef, Literal
from pytest_httpx import HTTPXMock
from rdflib.graph import _SubjectType

from bubble.ns import NT
from bubble.n3_utils import turtle
from bubble.capabilities import (
    InvocationContext,
    FileResult,
    http_client,
    get_file_metadata,
    create_result_node,
    do_post,
    do_shell,
)


@pytest.fixture
def graph():
    g = Graph()
    g.bind("nt", NT)
    return g


@pytest.fixture
def invocation():
    return URIRef("https://test.example/invocation")


@pytest.fixture
def shell_capability(graph, invocation):
    return InvocationContext(graph, invocation)


async def test_shell_capability_success(shell_capability):
    """Test successful shell command execution"""
    turtle_data = """
    @prefix nt: <https://node.town/2024/> .
    @base <https://test.example/> .

    <invocation> a nt:Invocation ;
        nt:provides [ a nt:ShellCommand ;
            nt:value 'echo "test" > $out' ] .
    """

    shell_capability.graph.parse(data=turtle_data, format="turtle")

    # Execute the command
    await do_shell(shell_capability)

    # Verify results
    result_node = next(
        shell_capability.graph.objects(shell_capability.invocation, NT.result)
    )
    assert result_node is not None

    # Check file path exists
    path = next(shell_capability.graph.objects(result_node, NT.path))
    assert Path(path).exists()

    # Verify content
    with open(path) as f:
        content = f.read().strip()
        assert content == "test"


async def test_shell_capability_failure(shell_capability):
    """Test shell command failure handling"""
    turtle_data = """
    @prefix nt: <https://node.town/2024/> .
    @base <https://test.example/> .

    <invocation> a nt:Invocation .
    """

    shell_capability.graph.parse(data=turtle_data, format="turtle")
    with pytest.raises(ValueError) as exc_info:
        await do_shell(shell_capability)
    assert "No" in str(exc_info.value)


async def test_shell_capability_with_stdin():
    """Test shell command with standard input"""
    graph = turtle("""
    @prefix nt: <https://node.town/2024/> .
    @base <https://test.example/> .

    <invocation> a nt:Invocation ;
        nt:provides [ a nt:ShellCommand ;
            nt:value "cat > $out" ] ;
        nt:provides [ a nt:StandardInput ;
            nt:value "test input" ] .
    """)

    invocation = URIRef("https://test.example/invocation")

    shell_capability = InvocationContext(graph, invocation)
    await do_shell(shell_capability)

    # Verify results
    (result_row, path) = shell_capability.select_one_row(
        "SELECT ?result ?path WHERE { ?invocation nt:result ?result . ?result nt:path ?path }"
    )

    assert Path(path).exists()

    # Verify content
    with open(path) as f:
        content = f.read().strip()
        assert content == "test input"


async def test_file_handler_metadata(tmp_path):
    """Test FileHandler metadata collection"""
    import trio

    test_file = tmp_path / "test.txt"
    async with await trio.open_file(str(test_file), "w") as f:
        await f.write("test content")

    result = await get_file_metadata(str(test_file))

    assert isinstance(result, FileResult)
    assert result.path == str(test_file)
    assert result.size is not None
    assert result.content_hash is not None
    assert result.creation_date is not None


async def test_create_result_node():
    """Test creating a result node in the graph"""
    graph = Graph()
    file_result = FileResult(path="/test/path", size=100, content_hash="abc123")

    result_node = await create_result_node(graph, file_result)

    assert (result_node, NT.path, Literal("/test/path")) in graph
    assert (result_node, NT.size, Literal(100)) in graph
    assert (result_node, NT.contentHash, Literal("abc123")) in graph


async def test_http_request_capability(httpx_mock: HTTPXMock):
    """Test HTTPRequestCapability"""
    turtle_data = """
    @prefix nt: <https://node.town/2024/> .
    @prefix json: <https://node.town/2024/json/#> .
    @base <https://test.example/> .

    <invocation> a nt:Invocation ;
        nt:provides <request> .

    <request> a nt:HTTPRequest ;
        nt:hasURL "https://example.com" ;
        nt:hasAuthorizationHeader "Bearer abc123" ;
        nt:posts [ a json:Object ;
            json:has [ json:key "key" ; json:val "value" ] ] .
    """

    graph = Graph()
    graph.parse(data=turtle_data, format="turtle")
    httpx_mock.add_response(
        url="https://example.com",
        method="POST",
        match_headers={"Authorization": "Bearer abc123"},
        match_json={"key": "value"},
    )

    async with httpx.AsyncClient() as client:
        http_client.set(client)
        invocation = URIRef("https://test.example/invocation")
        await do_post(InvocationContext(graph, invocation))
