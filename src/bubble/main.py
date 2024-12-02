import logging
import pathlib

import hypercorn
from rich import inspect
import structlog
import trio
import typer

from typer import Option
from rich.console import Console
from rich.logging import RichHandler

import bubble
from bubble.chat import BubbleChat
from bubble.cred import get_anthropic_credential
from bubble.http import serve
from bubble.repo import loading_bubble_from
from bubble.slop import Claude


logger = structlog.get_logger()

console = Console(width=80)

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
)

home = pathlib.Path.home()

BubblePath = Option(str(home / "bubble"), "--bubble", help="Bubble path")


@app.command()
def chat(
    bubble_path: str = BubblePath,
) -> None:
    """Chat with Claude about the bubble."""

    async def run():
        async with loading_bubble_from(trio.Path(bubble_path)):
            credential = await get_anthropic_credential()
            claude = Claude(credential)
            bubble_chat = BubbleChat(claude, console)
            await bubble_chat.run()

    trio.run(run)


@app.command()
def server(
    bubble_path: str = BubblePath,
    bind: str = Option("127.0.0.1:2024", "--bind", help="Bind address"),
) -> None:
    """Serve the Bubble web interface."""

    config = hypercorn.Config()
    config.bind = [bind]
    config.log.access_logger = logger.bind(name="http.access")
    config.log.error_logger = logger.bind(name="http")

    async def run():
        with bubble.http.bubble_path.bind(bubble_path):
            await serve(config)

    trio.run(run)
