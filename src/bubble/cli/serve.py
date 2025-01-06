"""Serve the bubble web interface."""

import os
from pathlib import Path
from urllib.parse import urlparse

import trio
import typer
import hypercorn
import structlog
import trio_asyncio
import hypercorn.trio
from typing import Any, Optional
from rdflib import PROV, SKOS, Graph, URIRef, Literal, Namespace

import swash.here as here
from swash.prfx import NT, RDF
from swash.util import add

from typer import Option
from bubble.cli.app import BaseUrl, RepoPath, app
from bubble.repo.repo import Repository
from bubble.repo.git import Git
from bubble.http.cert import generate_self_signed_cert
from bubble.http.town import Site
from bubble.mesh.base import this, spawn
from bubble.http.tools import ChatCreator, SheetEditor

logger = structlog.get_logger()
CONFIG = Namespace("https://bubble.node.town/vocab/config#")
app_dir = Path(typer.get_app_dir("bubble"))


async def run_server(app: Any, config: hypercorn.Config) -> None:
    """Run the server using hypercorn."""
    await hypercorn.trio.serve(app, config, mode="asgi")


def load_config(
    repo_path: str,
) -> tuple[
    str | None, str | None, str | None, str | None, str | None, bool
]:
    """Load configuration from config.ttl if it exists."""
    config_path = app_dir / "config.ttl"

    if not config_path.exists():
        logger.warning(
            "No config.ttl found. Run 'bubble init' to create one, "
            "or provide configuration through environment variables or command line options."
        )
        return None, None, None, None, None, False

    g = Graph()
    g.parse(config_path, format="turtle")

    config = URIRef("bubble:config")
    server_type = str(g.value(config, CONFIG.serverType))
    base_url = str(g.value(config, CONFIG.baseUrl))

    nats_url = g.value(config, CONFIG.natsUrl)
    if nats_url:
        nats_url = str(nats_url)

    if server_type == "self-signed":
        bind = f"{g.value(config, CONFIG.hostname)}:{g.value(config, CONFIG.port)}"
        cert_file = str(g.value(config, CONFIG.certFile))
        key_file = str(g.value(config, CONFIG.keyFile))
        self_signed = True
    elif server_type == "ssl":
        bind = f"{g.value(config, CONFIG.hostname)}:{g.value(config, CONFIG.port)}"
        cert_file = str(g.value(config, CONFIG.certFile))
        key_file = str(g.value(config, CONFIG.keyFile))
        self_signed = False
    else:  # http
        bind = f"{g.value(config, CONFIG.bindHost)}:{g.value(config, CONFIG.bindPort)}"
        cert_file = None
        key_file = None
        self_signed = False

    return bind, base_url, cert_file, key_file, nats_url, self_signed


@app.command()
def serve(
    bind: Optional[str] = Option(None, "--bind", help="Bind address"),
    base_url: Optional[str] = BaseUrl,
    repo_path: str = RepoPath,
    shell: bool = Option(False, "--shell", help="Start a bash subshell"),
    cert_file: Optional[str] = Option(
        None, "--cert", help="SSL certificate file path"
    ),
    key_file: Optional[str] = Option(
        None, "--key", help="SSL private key file path"
    ),
    self_signed: bool = Option(
        False,
        "--self-signed",
        help="Generate and use a self-signed certificate",
    ),
    nats_url: Optional[str] = Option(
        None, "--nats-url", help="NATS server URL"
    ),
) -> None:
    """Serve the bubble web interface."""
    # Try to load config.ttl first
    (
        config_bind,
        config_base_url,
        config_cert,
        config_key,
        config_nats_url,
        config_self_signed,
    ) = load_config(repo_path)

    # Command line args override config.ttl, which overrides environment variables
    if bind is None:
        bind = config_bind or os.environ.get(
            "BUBBLE_BIND", "127.0.0.1:2026"
        )
    if base_url is None:
        base_url = config_base_url or os.environ.get("BUBBLE_BASE")
    if cert_file is None:
        cert_file = config_cert or os.environ.get("BUBBLE_CERT")
    if key_file is None:
        key_file = config_key or os.environ.get("BUBBLE_KEY")
    if not self_signed:
        self_signed = config_self_signed
    if nats_url is None:
        nats_url = config_nats_url or os.environ.get("NATS_URL")

    if not any([cert_file, key_file, self_signed]):
        logger.info(
            "No SSL configuration found. Run 'bubble init' to configure SSL, "
            "or ensure HTTPS termination is handled by your reverse proxy."
        )

    trio_asyncio.run(
        _serve,
        bind,
        base_url,
        repo_path,
        shell,
        cert_file,
        key_file,
        self_signed,
        nats_url,
    )


async def _serve(
    bind: str,
    base_url: str,
    repo_path: str,
    shell: bool,
    cert_file: str | None = None,
    key_file: str | None = None,
    self_signed: bool = False,
    nats_url: Optional[str] = None,
) -> None:
    async def start_bash_shell():
        await trio.run_process(
            ["bash", "-i"],
            stdin=None,
            check=False,
            env={
                "PS1": get_bash_prompt(),
                "BASH_SILENCE_DEPRECATION_WARNING": "1",
            },
        )

    def get_bash_prompt():
        return r"\[\e[1m\][\[\e[34m\]town\[\e[0m\]\[\e[1m\]]\[\e[0m\] $ "

    config = hypercorn.Config()
    config.bind = [bind]
    config.log.error_logger = logger.bind(name="hypercorn.error")

    git = Git(trio.Path(repo_path))
    repo = await Repository.create(git, base_url)
    base_url = repo.get_base_url()
    hostname = urlparse(base_url).hostname
    assert hostname

    # Handle certificate configuration
    if self_signed:
        logger.info("Generating self-signed certificate")
        cert_file, key_file = generate_self_signed_cert(hostname)
        config.certfile = cert_file
        config.keyfile = key_file
    elif cert_file and key_file:
        config.certfile = cert_file
        config.keyfile = key_file

    logger.info(
        "starting Node.Town",
        repo_path=repo_path,
        base_url=base_url,
        ssl_enabled=config.ssl_enabled,
    )

    town = Site(base_url, bind, repo)

    if nats_url:
        logger.info("Setting up NATS clustering", nats_url=nats_url)
        await town.setup_nats(nats_url)

    async with trio.open_nursery() as nursery:
        here.site.set(Namespace(base_url))
        await repo.load_all()

        with town.install_context():
            with repo.using_new_buffer():
                town.vat.create_identity_graph()

                add(
                    this(),
                    {
                        RDF.type: NT.TownProcess,
                        PROV.generated: town.vat.identity_uri,
                        SKOS.prefLabel: Literal(
                            "server session", lang="en"
                        ),
                    },
                )

                town.vat.link_actor_to_identity(
                    await spawn(
                        nursery,
                        SheetEditor(),
                        name="sheet editor",
                    )
                )

                town.vat.link_actor_to_identity(
                    await spawn(
                        nursery,
                        ChatCreator(),
                        name="chat creator",
                    )
                )

                nursery.start_soon(
                    run_server, town.get_fastapi_app(), config
                )

                if shell:
                    await start_bash_shell()
                else:
                    while True:
                        await trio.sleep(1)
