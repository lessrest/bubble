import tempfile
from pathlib import Path
import trio
from rdflib import Graph
from typing import Sequence


async def reason(graphs: Sequence[Graph]) -> Graph:
    """Run the EYE reasoner on RDF graphs and return the resulting graph.

    Args:
        graphs: Sequence of RDF graphs to reason over

    Returns:
        Graph containing the reasoner output

    Raises:
        ValueError: If no input graphs are provided
    """
    if not graphs:
        raise ValueError("No input graphs provided")

    # Create temporary files for each graph
    temp_files = []
    async with trio.open_nursery() as nursery:
        for i, graph in enumerate(graphs):
            # Create temp file
            fd, path = tempfile.mkstemp(suffix='.n3')
            temp_files.append(path)
            
            # Write graph to temp file
            graph.serialize(path, format='n3')

    try:
        # Run EYE reasoner on temp files
        cmd = ["eye", "--nope", "--pass", *temp_files]
        
        with trio.move_on_after(1):
            result = await trio.run_process(
                cmd, capture_stdout=True, capture_stderr=True, check=True
            )

        # Parse result into new graph
        g = Graph()
        g.parse(data=result.stdout.decode(), format="n3")
        return g

    finally:
        # Clean up temp files
        for path in temp_files:
            Path(path).unlink(missing_ok=True)
