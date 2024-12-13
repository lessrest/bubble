import pathlib

from datetime import UTC, datetime
from urllib.parse import urlparse

import trio
import typer
import hypercorn
import hypercorn.trio

from typer import Option
from rdflib import Namespace, URIRef
from fastapi import FastAPI
from rich.console import Console

# import bubble

import swash.vars as vars
from swash.prfx import NT
from swash.util import add
from bubble.cert import generate_self_signed_cert
from bubble.chat import BubbleChat
from bubble.cred import get_anthropic_credential
from bubble.logs import configure_logging
from bubble.repo import loading_bubble_from
from bubble.slop import Claude
from bubble.town import (
    TownApp,
    SimpleSupervisor,
    spawn,
    txgraph,
)
from bubble.uptime import UptimeActor
from bubble.deepgram.talk import DeepgramClientActor

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


# @app.command()
# def server(
#     bubble_path: str = BubblePath,
#     bind: str = Option("127.0.0.1:2024", "--bind", help="Bind address"),
#     base_url: str = Option(
#         "https://localhost:2024", "--base-url", help="Public base URL"
#     ),
# ) -> None:
#     """Serve the Bubble web interface."""

#     config = hypercorn.Config()
#     config.bind = [bind]

#     if base_url.startswith("https://"):
#         hostname = urlparse(base_url).hostname
#         if hostname:
#             cert_path, key_path = generate_self_signed_cert(hostname)
#             config.certfile = cert_path
#             config.keyfile = key_path

#     async def run():
#         with bubble.http.bubble_path.bind(bubble_path):
#             await bubble.http.serve(config)

#     trio.run(run)


async def serve_fastapi_app(config: hypercorn.Config, app: FastAPI):
    await hypercorn.trio.serve(
        app,  # type: ignore
        config,
        mode="asgi",
    )


@app.command()
def town(
    bind: str = Option("127.0.0.1:2026", "--bind", help="Bind address"),
    base_url: str = Option(
        "https://localhost:2026/", "--base-url", help="Public base URL"
    ),
    bubble_path: str = BubblePath,
    shell: bool = Option(False, "--shell", help="Start a bash subshell"),
) -> None:
    """Serve the Town2 JSON-LD interface."""
    config = hypercorn.Config()
    config.bind = [bind]
    logger = configure_logging()
    config.log.error_logger = logger.bind(name="hypercorn.error")  # type: ignore

    assert base_url.startswith("https://")
    hostname = urlparse(base_url).hostname
    assert hostname

    # cert_path, key_path = generate_self_signed_cert(hostname)

    config.certfile = "./priv/localhost.pem"
    config.keyfile = "./priv/localhost-key.pem"

    async def run():
        async with trio.open_nursery() as nursery:
            logger.info(
                "starting Node.Town",
                bubble_path=bubble_path,
                base_url=base_url,
            )
            vars.site.set(Namespace(base_url))
            async with loading_bubble_from(trio.Path(bubble_path)) as repo:
                town = TownApp(base_url, bind, repo)
                with town.install_context():
                    # Create and persist the town's identity
                    async with txgraph():
                        town.system.create_identity_graph()

                    supervisor = await spawn(
                        nursery,
                        SimpleSupervisor(
                            DeepgramClientActor("Deepgram Client")
                        ),
                    )

                    # Link supervisor to the town's identity
                    async with txgraph():
                        town.system.link_actor_to_identity(supervisor)

                    uptime = await spawn(
                        nursery,
                        UptimeActor(datetime.now(UTC)),
                        name="uptime",
                    )

                    # Link uptime actor to the town's identity
                    async with txgraph():
                        town.system.link_actor_to_identity(uptime)

                    add(URIRef(base_url), {NT.environs: supervisor})
                    add(URIRef(base_url), {NT.environs: uptime})

                    nursery.start_soon(
                        serve_fastapi_app, config, town.get_fastapi_app()
                    )

                    if shell:
                        await start_bash_shell()
                    else:
                        while True:
                            await trio.sleep(1)

    async def start_bash_shell():
        await trio.run_process(
            ["bash", "-i"],
            stdin=None,
            check=False,
            env={
                # "CURL_CA_BUNDLE": cert_path,
                "PS1": get_bash_prompt(),
                "BASH_SILENCE_DEPRECATION_WARNING": "1",
            },
        )

    def get_bash_prompt():
        return r"\[\e[1m\][\[\e[32m\]town\[\e[0m\]\[\e[1m\]]\[\e[0m\] $ "

    trio.run(run)


if __name__ == "__main__":
    app()
