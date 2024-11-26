import trio
from rdflib import Graph


from typing import Sequence


async def reason(input_paths: Sequence[str]) -> Graph:
    """Run the EYE reasoner on N3 files and return the resulting graph.
    
    Args:
        input_paths: Paths to N3 files to reason over
        
    Returns:
        Graph containing the reasoner output
        
    Raises:
        ValueError: If no input files are provided
        FileNotFoundError: If any input file doesn't exist
    """
    if not input_paths:
        raise ValueError("No input files provided")
        
    # Verify all files exist
    for path in input_paths:
        if not Path(path).exists():
            raise FileNotFoundError(f"Input file not found: {path}")
            
    cmd = ["eye", "--nope", "--pass", *input_paths]

    with trio.move_on_after(1):
        result = await trio.run_process(
            cmd, capture_stdout=True, capture_stderr=True, check=True
        )

    g = Graph()
    g.parse(data=result.stdout.decode(), format="n3")
    return g
