import sys
import hashlib
import datetime
import tempfile
from typing import Optional, Tuple, List
from dataclasses import dataclass

import trio
import replicate
from rich import print, pretty
from rdflib import RDF, BNode, Graph, URIRef, Literal, Namespace
from rich.panel import Panel
from rich.syntax import Syntax
from rich.console import Console

console = Console()
pretty.install()

# Namespaces
SWA = Namespace("https://swa.sh/")
NT = Namespace("https://node.town/2024/")

# Constants
DEFAULT_BASE = "https://swa.sh/2024/11/22/step/1"
WEBP_SUFFIX = ".webp"


@dataclass
class FileResult:
    """Represents the result of a file operation"""
    path: str
    size: Optional[int] = None
    creation_date: Optional[datetime.datetime] = None
    content_hash: Optional[str] = None


class FileHandler:
    """Handles file operations and metadata collection"""
    
    @staticmethod
    async def create_result_node(graph: Graph, file_result: FileResult) -> BNode:
        result_node = BNode()
        graph.add((result_node, RDF.type, NT.LocalFile))
        graph.add((result_node, NT.path, Literal(file_result.path)))
        
        if file_result.creation_date:
            graph.add((result_node, NT.creationDate, Literal(file_result.creation_date)))
        if file_result.size:
            graph.add((result_node, NT.size, Literal(file_result.size)))
        if file_result.content_hash:
            graph.add((result_node, NT.contentHash, Literal(file_result.content_hash)))
            
        return result_node

    @staticmethod
    async def get_file_metadata(path: str) -> FileResult:
        stat = await trio.Path(path).stat()
        content = await trio.Path(path).read_bytes()
        
        return FileResult(
            path=path,
            size=stat.st_size,
            creation_date=datetime.datetime.fromtimestamp(stat.st_ctime, tz=datetime.timezone.utc),
            content_hash=hashlib.sha256(content).hexdigest()
        )


class N3Processor:
    """Processes N3 files and handles invocations"""
    def __init__(self, base: str = DEFAULT_BASE):
        self.base = base
        self.graph = Graph(base=base)
        self.file_handler = FileHandler()

    def print_n3(self) -> None:
        """Print the graph in N3 format"""
        n3 = self.graph.serialize(format="n3")
        n3 = n3.replace(
            "    ", "  "
        )  # Replace 4 spaces with 2 spaces globally
        print(Panel(Syntax(n3, "turtle"), title="N3"))

    def get_single_object(self, subject: URIRef, predicate: URIRef) -> Optional[URIRef]:
        """Get a single object for a subject-predicate pair"""
        objects = list(self.graph.objects(subject, predicate))
        if len(objects) != 1:
            return None
        return objects[0]

    def get_next_step(self, step: URIRef) -> Optional[URIRef]:
        """Get the next step in the process"""
        return self.get_single_object(step, SWA.precedes)

    def get_supposition(self, step: URIRef) -> Optional[URIRef]:
        """Get the supposition for a step"""
        return self.get_single_object(step, SWA.supposes)

    def get_invocation_details(self, invocation: URIRef) -> Tuple[Optional[URIRef], Optional[URIRef]]:
        """Get the parameter and target type for an invocation"""
        target = self.get_single_object(invocation, NT.target)
        target_type = self.get_single_object(target, RDF.type)
        parameter = self.get_single_object(invocation, NT.parameter)
        return parameter, target_type

    async def process_invocations(self, step: URIRef) -> None:
        """Process all invocations for a step"""
        invocations: List[URIRef] = list(self.graph.objects(step, SWA.invokes))
        if not invocations:
            return

        console.print(f"Processing {len(invocations)} invocations")
        console.rule()
        async with trio.open_nursery() as nursery:
            for invocation in invocations:
                parameter, target_type = self.get_invocation_details(
                    invocation
                )
                if target_type == NT.ShellCapability:
                    nursery.start_soon(
                        self.run_shell_command,
                        parameter,
                        invocation,
                    )
                elif target_type == NT.ArtGenerationCapability:
                    nursery.start_soon(
                        self.run_art_generation_command,
                        parameter,
                        invocation,
                    )

    async def run_shell_command(self, command: str, invocation: URIRef) -> None:
        """Run a shell command and store its results"""
        temp_dir = tempfile.mkdtemp()
        output_file = f"{temp_dir}/out"
        
        print(f"Running shell command: {command}")
        print(f"Working directory: {temp_dir}")
        console.rule()
        result = await trio.run_process(
            command,
            shell=True,
            cwd=temp_dir,
            env={"out": f"{temp_dir}/out"},
            capture_stderr=True,
        )
        if result.returncode != 0:
            print(f"Command failed: {result.returncode}")
            raise Exception(f"Command failed: {result.returncode}")

        try:
            file_result = await self.file_handler.get_file_metadata(output_file)
            result_node = await self.file_handler.create_result_node(self.graph, file_result)
            self.graph.add((invocation, SWA.result, result_node))
            
            print(f"Command output saved to: {output_file}")
            console.rule()
        except FileNotFoundError:
            pass

    async def run_art_generation_command(
        self, parameter: URIRef, invocation: URIRef
    ) -> None:
        """Generate art using the Replicate API"""
        prompt = self.get_single_object(parameter, NT.prompt)
        if not prompt:
            raise ValueError("No prompt found for art generation")

        print(f"Generating art for prompt: {prompt.value}")
        console.rule()
        result = await replicate.async_run(
            "black-forest-labs/flux-schnell",
            input={
                "prompt": prompt.value,
                "num_outputs": 1,
                "output_format": "webp",
            },
        )

        if isinstance(result, list):
            blob = await result[0].aread()
        else:
            blob = await result.aread()

        temp_file = tempfile.mktemp(suffix=WEBP_SUFFIX)
        async with await trio.open_file(temp_file, "wb") as f:
            await f.write(blob)

        file_result = FileResult(path=temp_file)
        result_node = await self.file_handler.create_result_node(self.graph, file_result)
        self.graph.add((invocation, SWA.result, result_node))

        print(f"Art generated and saved to: {temp_file}")
        console.rule()

    async def process(self) -> None:
        """Main processing method"""
        try:
            self.graph.parse(sys.stdin, format="n3")
            
            step = URIRef(f"{self.base}#")
            next_step = self.get_next_step(step)
            if not next_step:
                raise ValueError("No next step found in the graph")

            supposition = self.get_supposition(next_step)
            if not supposition:
                raise ValueError("No supposition found for the next step")

            await self.process_invocations(step)
            
        except Exception as e:
            console.print(f"[red]Error processing N3:[/red] {str(e)}")
            raise


def main() -> None:
    """Entry point for the N3 processor"""
    processor = N3Processor()
    trio.run(processor.process)


if __name__ == "__main__":
    main()
