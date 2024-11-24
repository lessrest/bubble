"""N3 processor for handling N3 files and invocations."""

import sys
import hashlib
import datetime
from typing import Sequence, Tuple, Optional
from dataclasses import dataclass
import trio
from rich import pretty
from rdflib import RDF, BNode, Graph, URIRef, Literal, Namespace
from rdflib.graph import _SubjectType, _ObjectType
from rich.console import Console
from pathlib import Path

from bubble.n3_utils import print_n3, get_single_object, get_objects

console = Console()
pretty.install()

# Namespaces
SWA = Namespace("https://swa.sh/")
NT = Namespace("https://node.town/2024/")

# Constants
DEFAULT_BASE = "https://swa.sh/2024/11/22/step/1"
CORE_RULES_PATH = Path(__file__).parent / "rules" / "core.n3"


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
    async def create_result_node(
        graph: Graph, file_result: FileResult
    ) -> BNode:
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

    @staticmethod
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


class StepExecution:
    """Engine for processing N3 files and applying rules"""

    def __init__(self, base: str = DEFAULT_BASE):
        self.base = base
        self.graph = Graph(base=base)
        self.file_handler = FileHandler()
        self.graph.parse(CORE_RULES_PATH, format="n3")

    def get_next_step(self, step: _SubjectType) -> _ObjectType:
        """Get the next step in the process"""
        return get_single_object(self.graph, step, NT.precedes)

    def get_supposition(self, step: _SubjectType) -> _ObjectType:
        """Get the supposition for a step"""
        return get_single_object(self.graph, step, NT.supposes)

    async def reason(self, input_paths: Sequence[str]) -> None:
        """Run the EYE reasoner on N3 files and update the processor's graph"""
        from bubble.n3_utils import reason

        self.graph = await reason(input_paths)

    def get_invocation_details(
        self, invocation: _SubjectType
    ) -> Tuple[_ObjectType, _ObjectType]:
        """Get the parameter and target type for an invocation"""
        target = get_single_object(self.graph, invocation, NT.invokes)
        target_type = get_single_object(self.graph, target, RDF.type)
        return target, target_type

    async def process_invocations(self, step: _SubjectType) -> None:
        """Process all invocations for a step"""
        from bubble.capabilities import ShellCapability, ArtGenerationCapability

        invocations = list(self.graph.objects(step, NT.invokes))
        if not invocations:
            return

        console.print(f"Processing {len(invocations)} invocations")
        console.rule()

        capability_map = {
            NT.ShellCapability: ShellCapability(),
            NT.ArtGenerationCapability: ArtGenerationCapability(),
        }

        async with trio.open_nursery() as nursery:
            for invocation in invocations:
                target, target_type = self.get_invocation_details(invocation)
                provides = get_objects(self.graph, invocation, NT.provides)

                if target_type in capability_map:
                    capability = capability_map[target_type]
                    nursery.start_soon(
                        capability.execute,
                        self.graph,
                        invocation,
                        target,
                        provides,
                    )

    async def process(self, n3_content: Optional[str] = None) -> None:
        """Main processing method"""
        try:
            if n3_content:
                self.graph.parse(data=n3_content, format="n3")
            else:
                self.graph.parse(sys.stdin, format="n3")

            step = URIRef(f"{self.base}#")
            next_step = self.get_next_step(step)
            if not next_step:
                raise ValueError("No next step found in the graph")

            print_n3(self.graph)

            supposition = self.get_supposition(next_step)
            if not supposition:
                raise ValueError("No supposition found for the next step")

            await self.process_invocations(step)

        except Exception as e:
            console.print(f"[red]Error processing N3:[/red] {str(e)}")
            raise


def main() -> None:
    """Entry point for the N3 processor"""
    processor = StepExecution()
    trio.run(processor.process)


if __name__ == "__main__":
    main()
