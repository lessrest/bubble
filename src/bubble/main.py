import pathlib
from urllib.parse import urlparse

import hypercorn
import hypercorn.trio
import trio
import typer

from typer import Option
from rich.console import Console

import bubble
from bubble.chat import BubbleChat
from bubble.cred import get_anthropic_credential
from bubble.repo import loading_bubble_from
from bubble.slop import Claude
from bubble.logs import configure_logging
from bubble.cert import generate_self_signed_cert


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
    base_url: str = Option(
        "https://localhost:2024", "--base-url", help="Public base URL"
    ),
) -> None:
    """Serve the Bubble web interface."""

    config = hypercorn.Config()
    config.bind = [bind]

    if base_url.startswith("https://"):
        hostname = urlparse(base_url).hostname
        if hostname:
            cert_path, key_path = generate_self_signed_cert(hostname)
            config.certfile = cert_path
            config.keyfile = key_path

    async def run():
        with bubble.http.bubble_path.bind(bubble_path):
            await bubble.http.serve(config)

    trio.run(run)


@app.command()
def town(
    bind: str = Option("127.0.0.1:2025", "--bind", help="Bind address"),
    base_url: str = Option(
        "https://localhost:2025", "--base-url", help="Public base URL"
    ),
) -> None:
    """Serve the Town websocket interface."""
    from bubble.town import new_town

    config = hypercorn.Config()
    config.bind = [bind]
    logger = configure_logging()
    config.log.error_logger = logger.bind(name="hypercorn.error")  # type: ignore

    if base_url.startswith("https://"):
        hostname = urlparse(base_url).hostname
        if hostname:
            cert_path, key_path = generate_self_signed_cert(hostname)
            config.certfile = cert_path
            config.keyfile = key_path

    async def run():
        app = await new_town(base_url, bind)
        await hypercorn.trio.serve(app, config, mode="asgi")  # type: ignore

    trio.run(run)
