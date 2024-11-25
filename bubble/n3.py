"""N3 processor for handling N3 files and invocations."""

from typing import Tuple, Optional
import trio
from rich import pretty
from rdflib import RDF, Graph, URIRef
from rdflib.graph import _SubjectType, _ObjectType
from rich.console import Console
from pathlib import Path
from glob import glob

from bubble.ns import NT
from bubble.capabilities import HTTPRequestCapability
from bubble.n3_utils import print_n3, get_single_object, get_objects

console = Console()
pretty.install()

# Constants
DEFAULT_BASE = "https://swa.sh/2024/11/22/step/1"
CORE_RULES_DIR = Path(__file__).parent / "rules"


class StepExecution:
    """Engine for processing N3 files and applying rules"""

    def __init__(self, step: Optional[str] = None, base: str = DEFAULT_BASE):
        self.step = step
        self.base = base
        self.graph = Graph(base=base)

        # Load all core rules from the rules directory
        core_rule_files = glob(str(CORE_RULES_DIR / "*.n3"))
        for rule_file in core_rule_files:
            self.graph.parse(rule_file, format="n3")

        # If a specific step file is provided, load it
        if step:
            if Path(step).is_dir():
                # If step is a directory, load all .n3 files in it
                n3_files = glob(str(Path(step) / "*.n3"))
                for n3_file in n3_files:
                    self.graph.parse(n3_file, format="n3")
            else:
                # Load single file
                self.graph.parse(step, format="n3")

    def get_next_step(self, step: _SubjectType) -> _ObjectType:
        """Get the next step in the process"""
        return get_single_object(self.graph, step, NT.precedes)

    def get_supposition(self, step: _SubjectType) -> _ObjectType:
        """Get the supposition for a step"""
        return get_single_object(self.graph, step, NT.supposes)

    async def reason(self) -> None:
        """Run the EYE reasoner on N3 files and update the processor's graph"""
        from bubble.n3_utils import reason

        if not self.step:
            raise ValueError("No step file provided")

        # Get all rule files for reasoning
        rule_files = glob(str(CORE_RULES_DIR / "*.n3"))

        # If step is a directory, get all n3 files, otherwise use the single file
        step_files = (
            glob(str(Path(self.step) / "*.n3"))
            if Path(self.step).is_dir()
            else [self.step]
        )

        # Combine all files for reasoning
        all_files = step_files + rule_files
        self.graph = await reason(all_files)

    def get_invocation_details(
        self, invocation: _SubjectType
    ) -> Optional[Tuple[_ObjectType, _ObjectType]]:
        """Get the parameter and target type for an invocation"""
        try:
            target = get_single_object(self.graph, invocation, NT.invokes)
            target_type = get_single_object(self.graph, target, RDF.type)
            return target, target_type
        except ValueError:
            return None

    async def process_invocations(self, step: _SubjectType) -> None:
        """Process all invocations for a step"""
        from bubble.capabilities import ShellCapability

        invocations = list(self.graph.objects(step, NT.invokes))
        if not invocations:
            return

        console.print(f"Processing {len(invocations)} invocations")
        console.rule()

        capability_map = {
            NT.ShellCapability: ShellCapability(),
            NT.POSTCapability: HTTPRequestCapability(),
        }

        async with trio.open_nursery() as nursery:
            for invocation in invocations:
                details = self.get_invocation_details(invocation)
                if details:
                    target, target_type = details
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

    async def process(self) -> None:
        """Main processing method"""
        try:
            step = URIRef(f"{self.base}#")
            next_step = self.get_next_step(step)
            if not next_step:
                raise ValueError("No next step found in the graph")

            print_n3(self.graph)

            supposition = self.get_supposition(next_step)
            if not supposition:
                raise ValueError("No supposition found for the next step")

            await self.process_invocations(step)

        except* Exception as e:
            for error in e.exceptions:
                console.print(f"[red]Error processing N3:[/red] {str(error)}")
                raise error
