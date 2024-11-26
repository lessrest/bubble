"""N3 processor for handling N3 files and invocations."""

from glob import glob
from typing import Optional
from pathlib import Path

import trio

from rich import pretty
from rdflib import URIRef
from rdflib.graph import _SubjectType
from rich.console import Console

from bubble.rdfutil import select_rows
from bubble.capabilities import InvocationContext, capability_map

console = Console()
pretty.install()

CORE_RULES_DIR = Path(__file__).parent / "rules"


class StepExecution:
    """Engine for processing N3 files and applying rules"""

    def __init__(self, base: str, step: Optional[str] = None):
        self.step = step
        self.base = base

    async def reason(self) -> None:
        """Run the EYE reasoner on N3 files and update the processor's graph"""
        from bubble.rdfutil import reason

        if not self.step:
            raise ValueError("No step file provided")

        # Get all rule files for reasoning
        rule_files = glob(str(CORE_RULES_DIR / "*.n3"))

        # If step is a directory, get all n3 files, otherwise use the
        # single file
        step_files = (
            glob(str(Path(self.step) / "*.n3"))
            if Path(self.step).is_dir()
            else [self.step]
        )

        # Combine all files for reasoning
        all_files = step_files + rule_files
        self.graph = await reason(all_files)

    async def process_invocations(self, step: _SubjectType) -> None:
        rows = select_rows(
            """
            SELECT ?invocation ?capability_type
            WHERE {
                ?invocation a nt:Invocation .
                ?step nt:invokes ?invocation .
                ?invocation nt:invokes ?target .
                ?target a ?capability_type .
            }
            """,
            {"step": step},
        )

        console.print(f"Processing {len(rows)} invocations")

        async with trio.open_nursery() as nursery:
            for invocation, capability_type in rows:
                cap = capability_map[capability_type]
                ctx = InvocationContext(invocation)
                nursery.start_soon(cap, ctx)

    async def process(self) -> None:
        """Main processing method"""
        try:
            step = URIRef(f"{self.base}#step")
            console.print(f"Processing step: {step}")
            await self.process_invocations(step)

        except* Exception as e:
            for error in e.exceptions:
                console.print(
                    f"[red]Error processing N3:[/red] {str(error)}"
                )
                raise error
