from pathlib import Path

import httpx
import pytest

from rdflib import Graph, URIRef, Literal
from pytest_httpx import HTTPXMock

from bubble import vars
from bubble.prfx import NT
from bubble.util import turtle
from bubble.caps import (
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
    """Create a test graph with JSON data"""
    with vars.graph.bind(Graph()) as g:
        g.bind("nt", NT)
        yield g


@pytest.fixture
def invocation():
    return URIRef("https://test.example/invocation")


@pytest.fixture
def shell_capability(invocation):
    return InvocationContext(invocation)


async def test_shell_capability_success(graph, shell_capability):
    """Test successful shell command execution"""
    turtle_data = """
    @prefix nt: <https://node.town/2024/> .
    @base <https://test.example/> .

    <invocation> a nt:Invocation ;
        nt:provides [ a nt:ShellCommand ;
            nt:value 'echo "test" > $out' ] .
    """

    graph.parse(data=turtle_data, format="turtle")

    # Execute the command
    await do_shell(shell_capability)

    # Verify results
    result_node = next(
        graph.objects(shell_capability.invocation, NT.result)
    )
    assert result_node is not None

    # Check file path exists
    path = next(graph.objects(result_node, NT.path))
    assert Path(path).exists()

    # Verify content
    with open(path) as f:
        content = f.read().strip()
        assert content == "test"


async def test_shell_capability_failure(graph, shell_capability):
    """Test shell command failure handling"""
    turtle_data = """
    @prefix nt: <https://node.town/2024/> .
    @base <https://test.example/> .

    <invocation> a nt:Invocation ;
        nt:provides [ a nt:ShellCommand ;
            nt:value 'exit 1' ] .
    """

    graph.parse(data=turtle_data, format="turtle")
    with pytest.raises(Exception) as exc_info:
        await do_shell(shell_capability)
    assert "Command 'exit 1' returned non-zero exit status 1" in str(
        exc_info.value
    )


@pytest.mark.trio
async def test_shell_no_output_file(graph, shell_capability):
    """Test handling when command doesn't create output file"""
    turtle_data = """
    @prefix nt: <https://node.town/2024/> .
    @base <https://test.example/> .

    <invocation> a nt:Invocation ;
        nt:provides [ a nt:ShellCommand ;
            nt:value 'true' ] .
    """

    graph.parse(data=turtle_data, format="turtle")
    await do_shell(shell_capability)

    # Verify no result node was created
    # When no output file is created, that's fine - there should be no result node
    results = shell_capability.select_one_row(
        """
        SELECT (COUNT(*) as ?count)
        WHERE {
            ?invocation nt:result ?result
        }
        """,
        {"invocation": shell_capability.invocation},
    )
    assert int(results[0]) == 0  # Count should be 0 indicating no results


@pytest.mark.trio
async def test_shell_invalid_command(graph, shell_capability):
    """Test handling of invalid shell command"""
    turtle_data = """
    @prefix nt: <https://node.town/2024/> .
    @base <https://test.example/> .

    <invocation> a nt:Invocation ;
        nt:provides [ a nt:ShellCommand ;
            nt:value 'nonexistentcommand' ] .
    """

    graph.parse(data=turtle_data, format="turtle")
    with pytest.raises(Exception) as exc_info:
        await do_shell(shell_capability)
    assert (
        "Command 'nonexistentcommand' returned non-zero exit status 127"
        in str(exc_info.value)
    )


async def test_shell_capability_with_stdin():
    """Test shell command with standard input"""
    with vars.graph.bind(
        turtle("""
        @prefix nt: <https://node.town/2024/> .
        @base <https://test.example/> .

        <invocation> a nt:Invocation ;
            nt:provides [ a nt:ShellCommand ;
                nt:value "cat > $out" ] ;
            nt:provides [ a nt:StandardInput ;
                nt:value "test input" ] .
        """)
    ):
        invocation = URIRef("https://test.example/invocation")

        shell_capability = InvocationContext(invocation)
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
    with vars.graph.bind(Graph()) as graph:
        file_result = FileResult(
            path="/test/path", size=100, content_hash="abc123"
        )

        result_node = await create_result_node(file_result)

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

    with vars.graph.bind(Graph()) as graph:
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
            await do_post(InvocationContext(invocation))
