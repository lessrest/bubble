from urllib.parse import urlparse, urljoin

from fastapi import FastAPI
import trio
import hypercorn
import structlog
import hypercorn.trio
import trio_asyncio
from typer import Option

from rdflib import PROV, SKOS, Literal, Namespace

import swash.here as here

from swash.prfx import NT, RDF
from swash.util import add
from bubble.http.tool import SheetEditor
from bubble.http.town import Site
from bubble.mesh.mesh import this, spawn
from bubble.repo.repo import Git, Repository
from bubble.http.cert import generate_self_signed_cert
from bubble.cli.app import app, RepoPath

logger = structlog.get_logger()


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
    repo_path: str = RepoPath,
    shell: bool = Option(False, "--shell", help="Start a bash subshell"),
    cert_file: str = Option(
        None, "--cert", help="SSL certificate file path"
    ),
    key_file: str = Option(None, "--key", help="SSL private key file path"),
    self_signed: bool = Option(
        False,
        "--self-signed",
        help="Generate and use a self-signed certificate",
    ),
) -> None:
    """Serve the Node.Town web interface. Uses HTTP if no certificate/key provided, assuming HTTPS termination by reverse proxy."""
    trio_asyncio.run(
        _bubble_town,
        bind,
        base_url,
        repo_path,
        shell,
        cert_file,
        key_file,
        self_signed,
    )


async def _bubble_town(
    bind: str,
    base_url: str,
    repo_path: str,
    shell: bool,
    cert_file: str | None = None,
    key_file: str | None = None,
    self_signed: bool = False,
):
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
    config.log.error_logger = logger.bind(name="hypercorn.error")  # type: ignore

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
    else:
        # Use HTTP when no certificates are provided
        logger.info(
            "Running in HTTP mode - ensure HTTPS termination is handled by your reverse proxy"
        )

    async with trio.open_nursery() as nursery:
        logger.info(
            "starting Node.Town",
            repo_path=repo_path,
            base_url=base_url,
            ssl_enabled=config.ssl_enabled,
        )
        here.site.set(Namespace(base_url))

        await repo.load_all()

        town = Site(base_url, bind, repo)
        with town.install_context():
            with repo.new_graph():
                town.vat.create_identity_graph()

                add(
                    this(),
                    {
                        RDF.type: NT.TownProcess,
                        PROV.generated: town.vat.get_identity_uri(),
                        SKOS.prefLabel: Literal(
                            "root town process", lang="en"
                        ),
                    },
                )

                editor = await spawn(
                    nursery,
                    SheetEditor(this()),
                    name="sheet editor",
                )

                # Link supervisor to the town's identity
                town.vat.link_actor_to_identity(editor)

                nursery.start_soon(
                    serve_fastapi_app, config, town.get_fastapi_app()
                )

                if shell:
                    await start_bash_shell()
                else:
                    while True:
                        await trio.sleep(1)
