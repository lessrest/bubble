import trio
from rdflib import Graph


from typing import Sequence


async def reason(input_paths: Sequence[str]) -> Graph:
    """Run the EYE reasoner on N3 files and return the resulting graph"""
    cmd = ["eye", "--nope", "--pass", *input_paths]

    with trio.move_on_after(1):
        result = await trio.run_process(
            cmd, capture_stdout=True, capture_stderr=True, check=True
        )

    g = Graph()
    g.parse(data=result.stdout.decode(), format="n3")
    return g
