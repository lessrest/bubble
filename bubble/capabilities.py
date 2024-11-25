import tempfile

from abc import ABC, abstractmethod
from typing import Iterable

from rich import inspect
import trio

from rdflib import Graph, URIRef, RDF
from rich.console import Console

from bubble.n3_utils import get_json_value, json_to_n3, print_n3

console = Console()


class Capability(ABC):
    """Abstract base class for all capabilities"""

    @abstractmethod
    async def execute(
        self, parameter: URIRef, invocation: URIRef, graph: Graph
    ) -> None:
        """Execute the capability with given parameters"""
        pass


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
        from bubble.n3 import NT

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
            from bubble.n3 import FileHandler

            file_result = await FileHandler.get_file_metadata(output_file)
            result_node = await FileHandler.create_result_node(
                graph, file_result
            )
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
        from bubble.n3 import NT

        from bubble.n3_utils import get_single_object

        requests = list(provides)
        if len(requests) != 1:
            raise ValueError("No request provided")

        request = requests[0]
        inspect(request)

        # get the url
        url = get_single_object(graph, request, NT.hasURL)
        inspect(url)

        # get the post
        post = get_single_object(graph, request, NT.posts)
        inspect(post)

        post_value = get_json_value(graph, post)
        inspect(post_value)

        bearer = get_single_object(graph, request, NT.hasAuthorizationHeader)
        inspect(bearer)

        client = httpx.AsyncClient()
        response = await client.request(
            method="POST",
            url=url,
            json=post_value,
            headers={"Authorization": bearer},
        )

        response_value = response.json()

        inspect(response_value)

        result_node = json_to_n3(graph, response_value)
        inspect(result_node)
        graph.add((invocation, NT.result, result_node))
        print_n3(graph)
