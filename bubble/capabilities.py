import tempfile

from abc import ABC, abstractmethod

import trio
import replicate

from rdflib import Graph, URIRef, RDF
from rich.console import Console

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
        self, parameter: URIRef, invocation: URIRef, graph: Graph
    ) -> None:
        """Execute shell command with optional standard input"""
        from bubble.n3 import NT

        temp_dir = tempfile.mkdtemp()
        output_file = f"{temp_dir}/out"

        # Get command and stdin values
        command = None
        stdin = None

        for provided in graph.objects(invocation, NT.provides):
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
            from bubble.n3 import SWA, FileHandler

            file_result = await FileHandler.get_file_metadata(output_file)
            result_node = await FileHandler.create_result_node(
                graph, file_result
            )
            graph.add((invocation, SWA.result, result_node))

            print(f"Command output saved to: {output_file}")
            console.rule()
        except FileNotFoundError:
            pass


class ArtGenerationCapability(Capability):
    """Handles art generation using Replicate API"""

    WEBP_SUFFIX = ".webp"

    async def execute(
        self, parameter: URIRef, invocation: URIRef, graph: Graph
    ) -> None:
        from bubble.n3 import NT, SWA, FileHandler

        prompt = next(graph.objects(parameter, NT.prompt), None)
        if not prompt:
            raise ValueError("No prompt found for art generation")

        print(f"Generating art for prompt: {prompt}")
        console.rule()

        result = await replicate.async_run(
            "black-forest-labs/flux-schnell",
            input={
                "prompt": prompt,
                "num_outputs": 1,
                "output_format": "webp",
            },
        )

        async for blob in result:
            temp_file = tempfile.mktemp(suffix=self.WEBP_SUFFIX)
            async with await trio.open_file(temp_file, "wb") as f:
                await f.write(blob)

            from bubble.n3 import FileResult

            file_result = FileResult(path=temp_file)
            result_node = await FileHandler.create_result_node(
                graph, file_result
            )
            graph.add((invocation, SWA.result, result_node))

            print(f"Art generated and saved to: {temp_file}")
            console.rule()
