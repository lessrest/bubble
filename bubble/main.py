import logging
import pathlib

import trio
import typer

from typer import Option
from rich.console import Console
from rich.logging import RichHandler

from bubble.chat import BubbleChat
from bubble.cred import get_anthropic_credential
from bubble.repo import loading_bubble_from
from bubble.slop import Claude

FORMAT = "%(message)s"
logging.basicConfig(
    level=logging.WARNING,
    format=FORMAT,
    datefmt="[%X]",
    handlers=[RichHandler()],
)

logger = logging.getLogger(__name__)
console = Console(width=80)

app = typer.Typer(add_completion=False)

home = pathlib.Path.home()


@app.command()
def chat(
    bubble_path: str = Option(
        str(home / "bubble"), "--bubble", help="Bubble path"
    ),
) -> None:
    """Process N3 files with optional reasoning and skolemization."""

    async def run():
        async with loading_bubble_from(trio.Path(bubble_path)):
            credential = await get_anthropic_credential()
            claude = Claude(credential)
            bubble_chat = BubbleChat(claude, console)
            await bubble_chat.run()

    trio.run(run)
