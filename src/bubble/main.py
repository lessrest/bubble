from functools import partial
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
from bubble.town.cert import generate_self_signed_cert


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
    from bubble.town.town import new_town

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


@app.command()
def town2(
    bind: str = Option("127.0.0.1:2026", "--bind", help="Bind address"),
    base_url: str = Option(
        "https://localhost:2026", "--base-url", help="Public base URL"
    ),
    bubble_path: str = BubblePath,
) -> None:
    """Serve the Town2 JSON-LD interface."""
    from bubble.town.town2 import town_app

    config = hypercorn.Config()
    config.bind = [bind]
    logger = configure_logging()
    config.log.error_logger = logger.bind(name="hypercorn.error")  # type: ignore

    assert base_url.startswith("https://")
    hostname = urlparse(base_url).hostname
    assert hostname
    cert_path, key_path = generate_self_signed_cert(hostname)
    config.certfile = cert_path
    config.keyfile = key_path

    async def run():
        async with trio.open_nursery() as nursery:
            logger.info("starting town2", bubble_path=bubble_path)
            async with loading_bubble_from(trio.Path(bubble_path)) as repo:
                app = town_app(base_url, bind, repo)

                async def serve():
                    try:
                        await hypercorn.trio.serve(app, config, mode="asgi")  # type: ignore
                    except trio.Cancelled:
                        pass
                    except Exception as e:
                        logger.error("error serving town2", error=e)
                        raise

                nursery.start_soon(serve)
                logger.info("starting bash")
                try:
                    await start_bash_shell()
                except trio.Cancelled:
                    pass
                except Exception as e:
                    logger.error("error starting bash", error=e)
                    raise

                logger.info("shutting down")
                nursery.cancel_scope.cancel()

    async def start_bash_shell():
        await trio.run_process(
            ["bash", "-i"],
            stdin=None,
            check=False,
            env={
                "CURL_CA_BUNDLE": cert_path,
                "PS1": get_bash_prompt(),
                "BASH_SILENCE_DEPRECATION_WARNING": "1",
            },
        )

    def get_bash_prompt():
        return r"\[\e[1m\][\[\e[32m\]town\[\e[0m\]\[\e[1m\]]\[\e[0m\] $ "

    trio.run(run)


if __name__ == "__main__":
    app()
