from dataclasses import dataclass
import datetime
import hashlib
import tempfile

from abc import ABC, abstractmethod
from typing import Iterable, Optional

import trio

from rdflib import BNode, Graph, Literal, URIRef, RDF
from rich.console import Console

from bubble.ns import NT
from bubble.n3_utils import get_json_value, json_to_n3

console = Console()


class Capability(ABC):
    """Abstract base class for all capabilities"""

    @abstractmethod
    async def execute(
        self, parameter: URIRef, invocation: URIRef, graph: Graph
    ) -> None:
        """Execute the capability with given parameters"""
        pass


@dataclass
class FileResult:
    """Represents the result of a file operation"""

    path: str
    size: Optional[int] = None
    creation_date: Optional[datetime.datetime] = None
    content_hash: Optional[str] = None


async def create_result_node(graph: Graph, file_result: FileResult) -> BNode:
    result_node = BNode()
    graph.add((result_node, RDF.type, NT.LocalFile))
    graph.add((result_node, NT.path, Literal(file_result.path)))

    if file_result.creation_date:
        graph.add(
            (
                result_node,
                NT.creationDate,
                Literal(file_result.creation_date),
            )
        )
    if file_result.size:
        graph.add((result_node, NT.size, Literal(file_result.size)))
    if file_result.content_hash:
        graph.add(
            (result_node, NT.contentHash, Literal(file_result.content_hash))
        )

    return result_node


async def get_file_metadata(path: str) -> FileResult:
    stat = await trio.Path(path).stat()
    content = await trio.Path(path).read_bytes()

    return FileResult(
        path=path,
        size=stat.st_size,
        creation_date=datetime.datetime.fromtimestamp(
            stat.st_ctime, tz=datetime.timezone.utc
        ),
        content_hash=hashlib.sha256(content).hexdigest(),
    )


class ShellCapability(Capability):
    """Handles shell command execution"""

    async def execute(
        self,
        graph: Graph,
        invocation: URIRef,
        target: URIRef,
        provides: Iterable[URIRef],
    ) -> None:
        """Execute shell command with optional standard input"""
        from bubble.ns import NT

        temp_dir = tempfile.mkdtemp()
        output_file = f"{temp_dir}/out"

        # Get command and stdin values
        command = None
        stdin = None

        for provided in provides:
            ptype = next(graph.objects(provided, RDF.type))
            if ptype == NT.ShellCommand:
                command = str(next(graph.objects(provided, NT.value)))
            elif ptype == NT.StandardInput:
                stdin = str(next(graph.objects(provided, NT.value)))

        if not command:
            raise ValueError("No shell command provided")

        print(f"Running shell command: {command}")
        print(f"Working directory: {temp_dir}")
        if stdin:
            print(f"With standard input: {stdin[:50]}...")
        console.rule()

        result = await trio.run_process(
            command,
            shell=True,
            cwd=temp_dir,
            env={"out": f"{temp_dir}/out"},
            capture_stderr=True,
            stdin=stdin.encode() if stdin else None,
        )
        if result.returncode != 0:
            print(f"Command failed: {result.returncode}")
            raise Exception(f"Command failed: {result.returncode}")

        try:
            file_result = await get_file_metadata(output_file)
            result_node = await create_result_node(graph, file_result)

            graph.add((invocation, NT.result, result_node))

            print(f"Command output saved to: {output_file}")
            console.rule()
        except FileNotFoundError:
            pass


class HTTPRequestCapability(Capability):
    """Handles HTTP requests"""

    async def execute(
        self,
        graph: Graph,
        invocation: URIRef,
        target: URIRef,
        provides: Iterable[URIRef],
    ) -> None:
        # we'll use httpx to do the request
        import httpx
        from bubble.ns import NT

        from bubble.n3_utils import get_single_object

        requests = list(provides)
        if len(requests) != 1:
            raise ValueError("No request provided")

        request = requests[0]

        url = get_single_object(graph, request, NT.hasURL)
        post = get_single_object(graph, request, NT.posts)
        post_value = get_json_value(graph, post)
        bearer = get_single_object(graph, request, NT.hasAuthorizationHeader)

        client = httpx.AsyncClient()
        response = await client.request(
            method="POST",
            url=url,
            json=post_value,
            headers={"Authorization": bearer},
        )

        response_value = response.json()

        result_node = json_to_n3(graph, response_value)
        graph.add((invocation, NT.result, result_node))
