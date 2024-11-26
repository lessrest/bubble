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
def show(
    input_path: str = Option(
        str(home / "bubble"), "--input", "-i", help="Input N3 file path"
    ),
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
