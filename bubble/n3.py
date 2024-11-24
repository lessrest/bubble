import sys
import hashlib
import datetime
import subprocess

from typing import List, Tuple, Optional
from dataclasses import dataclass

import trio

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
                (
                    result_node,
                    NT.contentHash,
                    Literal(file_result.content_hash),
                )
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


class N3Processor:
    """Processes N3 files and handles invocations"""

    def __init__(self, base: str = DEFAULT_BASE):
        self.base = base
        self.graph = Graph(base=base)
        self.file_handler = FileHandler()

    def print_n3(self) -> None:
        """Print the graph in N3 format"""
        n3 = self.graph.serialize(format="n3")
        n3 = n3.replace("    ", "  ")  # Replace 4 spaces with 2 spaces globally
        print(Panel(Syntax(n3, "turtle"), title="N3"))

    def get_single_object(
        self, subject: URIRef, predicate: URIRef
    ) -> Optional[URIRef]:
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

    def get_invocation_details(
        self, invocation: URIRef
    ) -> Tuple[Optional[URIRef], Optional[URIRef]]:
        """Get the parameter and target type for an invocation"""
        target = self.get_single_object(invocation, NT.target)
        target_type = self.get_single_object(target, RDF.type)
        parameter = self.get_single_object(invocation, NT.parameter)
        return parameter, target_type

    async def process_invocations(self, step: URIRef) -> None:
        """Process all invocations for a step"""
        from bubble.capabilities import ShellCapability, ArtGenerationCapability

        invocations: List[URIRef] = list(self.graph.objects(step, SWA.invokes))
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
                parameter, target_type = self.get_invocation_details(invocation)

                if target_type in capability_map:
                    capability = capability_map[target_type]
                    nursery.start_soon(
                        capability.execute,
                        parameter,
                        invocation,
                        self.graph,
                    )

    async def process(self, n3_content: str = None) -> None:
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

            supposition = self.get_supposition(next_step)
            if not supposition:
                raise ValueError("No supposition found for the next step")

            await self.process_invocations(step)

        except Exception as e:
            console.print(f"[red]Error processing N3:[/red] {str(e)}")
            raise

    async def reason(self, input_path: str) -> Graph:
        """Run the EYE reasoner on an N3 file and return the resulting graph"""
        # Run EYE reasoner
        cmd = ["eye", "--quiet", "--nope", "--pass-all", input_path]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        # Parse the output into a new graph
        g = Graph()
        g.parse(data=result.stdout, format="n3")
        return g

    def show(self, input_path: str) -> Graph:
        """Load and normalize an N3 file"""
        g = Graph()
        g.parse(input_path, format="n3")
        return g

    def skolemize(
        self,
        input_path: str,
        namespace: str = "https://swa.sh/.well-known/genid/",
    ) -> Graph:
        """Convert blank nodes in an N3 file to fresh IRIs"""
        from bubble.id import Mint

        mint = Mint()

        # Create input graph and parse file
        g = Graph()
        g.parse(input_path, format="n3")

        # Create namespace for new IRIs
        ns = Namespace(namespace)

        # Create output graph
        g_sk = Graph()

        # Copy namespace bindings
        for prefix, namespace in g.namespaces():
            g_sk.bind(prefix, namespace)

        # Bind swa to the Skolem namespace
        g_sk.bind("swa", ns)

        # Create mapping of blank nodes to IRIs
        bnode_map = {}

        # Helper function to get or create IRI for a blank node
        def get_iri_for_bnode(bnode):
            if bnode not in bnode_map:
                bnode_map[bnode] = mint.fresh_casual_iri(ns)
            return bnode_map[bnode]

        # Copy all triples, consistently replacing blank nodes
        for s, p, o in g:
            s_new = get_iri_for_bnode(s) if isinstance(s, BNode) else s
            o_new = get_iri_for_bnode(o) if isinstance(o, BNode) else o
            g_sk.add((s_new, p, o_new))

        return g_sk


def main() -> None:
    """Entry point for the N3 processor"""
    processor = N3Processor()
    trio.run(processor.process)


if __name__ == "__main__":
    main()
