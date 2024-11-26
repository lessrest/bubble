import pathlib

from typing import Optional

import trio
import typer

from rich import inspect
from typer import Option
from rich.console import Console

from bubble.id import Mint
from bubble.repo import Bubble
from bubble.n3_utils import print_n3

console = Console(width=80)

app = typer.Typer(add_completion=False)

home = pathlib.Path.home()


@app.command()
def main(
    input_path: str = Option(
        str(home / "bubble"), "--input", "-i", help="Input N3 file path"
    ),
    output_path: Optional[str] = Option(
        None, "--output", "-o", help="Output file path (defaults to stdout)"
    ),
    reason: bool = Option(
        False, "--reason", "-r", help="Run the EYE reasoner on the input"
    ),
    skolem: bool = Option(
        False, "--skolem", "-s", help="Convert blank nodes to IRIs"
    ),
    invoke: bool = Option(False, "--invoke", help="Invoke capabilities"),
) -> None:
    """Process N3 files with optional reasoning and skolemization."""

    async def run():
        mint = Mint()
        path = trio.Path(input_path)
        bubble = await Bubble.open(path, mint)
        inspect(bubble)
        print_n3(bubble.graph)

    trio.run(run)


if __name__ == "__main__":
    app()
