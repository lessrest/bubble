import pathlib
import os

from datetime import UTC, datetime
import sys
from urllib.parse import urlparse

from fastapi import FastAPI, WebSocket
import rdflib
import rdflib.collection
from swash.html import document
from swash.mint import fresh_id
from swash.rdfa import autoexpanding, rdf_resource
import trio
import trio_asyncio
import typer
import hypercorn
import hypercorn.trio

from typer import Option
from rdflib import SKOS, BNode, Literal, URIRef, Namespace, PROV, DCAT, XSD
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from cryptography.hazmat.primitives.asymmetric import ed25519

import swash.vars as vars

from swash.prfx import NT, RDF
from swash.util import add, new
from bubble.data import Git, Repository, context
from bubble.mesh import SimpleSupervisor, spawn, this, txgraph
from bubble.logs import configure_logging
from bubble.stat.stat import gather_system_info
from bubble.town import (
    Site,
)
from bubble.mesh import UptimeActor
from bubble.deepgram.talk import DeepgramClientActor
from bubble.join import (
    handle_messages,
    receive_datasets,
    signed_connection,
    anonymous_connection,
)
from swash.lynx import render_html
from bubble.replicate.make import ReplicateClientActor, make_image
from bubble.data import from_env

import logging

console = Console(width=80)

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
)

home = pathlib.Path.home()

RepoPath = Option(str(home / "repo"), "--repo", help="Repository path")


def get_log_level() -> int:
    """Get logging level from environment variable."""
    debug = os.environ.get("BUBBLE_DEBUG", "").lower()
    if debug in ("1", "true", "yes"):
        return logging.DEBUG
    return logging.INFO


@app.command()
def shell(
    repo_path: str = RepoPath,
    namespace: str = Option(
        "https://example.com/", "--namespace", help="Namespace"
    ),
) -> None:
    """Create a new repository and start a shell session."""

    logger = configure_logging(level=get_log_level())

    async def run():
        git = Git(trio.Path(repo_path))
        await git.init()
        repo = await Repository.create(git, namespace=Namespace(namespace))
        await repo.save_all()
        await repo.commit("new repository")

        system_info = await gather_system_info()
        user = system_info["user_info"]

        with repo.new_graph():
            with repo.new_agent(
                NT.Account,
                {
                    NT.owner: user.pw_gecos,
                },
            ) as agent:
                arguments = BNode()
                rdflib.collection.Collection(
                    context.graph.get(),
                    arguments,
                    [Literal(arg) for arg in sys.argv[1:]],
                )
                # Start a new shell session activity
                with repo.new_activity(
                    NT.InteractiveShellSession,
                    {
                        PROV.wasStartedBy: new(
                            NT.Command,
                            {
                                NT.programPath: Literal(sys.argv[0]),
                                NT.arguments: arguments,
                            },
                        )
                    },
                ) as activity:
                    # Create a derived graph for the shell session
                    with repo.new_derived_graph(
                        source_graph=repo.metadata_id
                    ) as derived_id:
                        # Get the directory path for this graph
                        graph_dir = repo.graph_dir(derived_id)
                        await graph_dir.mkdir(parents=True, exist_ok=True)

                        await repo.save_all()
                        await repo.commit("new shell session")

                        logger.info(
                            "Starting shell session",
                            graph=derived_id,
                            activity=activity,
                            directory=str(graph_dir),
                        )

                        # Start bash with environment variables set and cwd set to graph directory
                        await trio.run_process(
                            ["bash", "-i"],
                            stdin=None,
                            check=False,
                            cwd=str(graph_dir),
                            env={
                                "BUBBLE": repo_path,
                                "BUBBLE_GRAPH": str(derived_id),
                                "BUBBLE_GRAPH_DIR": str(graph_dir),
                                "BUBBLE_ACTIVITY": str(activity),
                                "BUBBLE_AGENT": str(agent),
                                "PS1": r"\n\[\e[1m\]\[\e[34m\]"
                                + derived_id.n3()
                                + " @ "
                                + system_info["hostname"]
                                + r" \[\e[0m\]\[\e[1m\]\[\e[0m\]\n $ ",
                                "BASH_SILENCE_DEPRECATION_WARNING": "1",
                                # Inherit parent environment
                                **os.environ,
                            },
                        )

                        # After shell exits, commit any changes
                        await repo.save_all()
                        await repo.commit("Update after shell session")

    trio.run(run)


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
) -> None:
    """Serve the Town2 JSON-LD interface."""
    config = hypercorn.Config()
    config.bind = [bind]
    logger = configure_logging(level=get_log_level())
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
                repo_path=repo_path,
                base_url=base_url,
            )
            vars.site.set(Namespace(base_url))
            repo = await Repository.create(
                Git(trio.Path(repo_path)),
                namespace=Namespace(base_url),
            )

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

                    supervisor = await spawn(
                        nursery,
                        SimpleSupervisor(
                            {
                                "Deepgram client": DeepgramClientActor(),
                                "Replicate client": ReplicateClientActor(
                                    repo
                                ),
                            }
                        ),
                        name="actor supervisor",
                    )

                    # Link supervisor to the town's identity
                    town.vat.link_actor_to_identity(supervisor)

                    # Add image gallery link to the root
                    add(
                        URIRef(base_url),
                        {
                            NT.affordance: new(
                                NT.Link,
                                {
                                    NT.label: Literal(
                                        "Image Gallery", "en"
                                    ),
                                    NT.href: Literal(
                                        "/images", datatype=XSD.anyURI
                                    ),
                                },
                            )
                        },
                    )

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
        return r"\[\e[1m\][\[\e[34m\]town\[\e[0m\]\[\e[1m\]]\[\e[0m\] $ "

    trio_asyncio.run(run)


@app.command()
def join_simple(
    town: str = Option(..., "--town", help="Town URL to join"),
    anonymous: bool = Option(
        False, "--anonymous", help="Join anonymously without an identity"
    ),
) -> None:
    """Join a remote town as a simple peer that prints incoming messages."""
    logger = configure_logging(level=get_log_level())

    async def run():
        try:
            if anonymous:
                async with anonymous_connection(town) as (ws, me):
                    await handle_dataset_receiving(ws, me)

            else:
                sec, pub = generate_key_pair()
                async with signed_connection(town, sec, pub) as (ws, me):
                    await handle_dataset_receiving(ws, me)

        except Exception as e:
            logger.error("connection failed", error=e)
            raise

    async def handle_dataset_receiving(ws: WebSocket, actor_uri: URIRef):
        logger.info("connected to town", actor_uri=actor_uri)
        async for msg in receive_datasets(ws):
            logger.info("Received dataset", graph=msg)

    def generate_key_pair():
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        return private_key, public_key

    trio.run(run)


@app.command()
def info() -> None:
    """Display information about the current bubble environment and graphs."""
    console = Console(width=78)
    configure_logging(level=get_log_level())

    # Check if we're in a bubble environment
    if "BUBBLE" not in os.environ:
        console.print(
            Panel(
                "No bubble environment detected. Use [bold]bubble shell[/] to create one.",
                title="Bubble Status",
                border_style="yellow",
            )
        )
        return

    async def run():
        try:
            async with from_env() as repo:
                # Create environment info table
                env_table = Table(box=box.ROUNDED, title="Environment")
                env_table.add_column("Key", style="bold blue")
                env_table.add_column("Value")

                env_table.add_row("Bubble Path", os.environ["BUBBLE"])
                env_table.add_row(
                    "Current Graph", os.environ["BUBBLE_GRAPH"]
                )
                env_table.add_row(
                    "Graph Directory",
                    os.environ.get("BUBBLE_GRAPH_DIR", "-"),
                )

                console.print(env_table)

                # Create graphs info table
                graphs_table = Table(box=box.ROUNDED, title="Graphs")
                graphs_table.add_column("Graph", style="bold")
                graphs_table.add_column("Type")
                graphs_table.add_column("Created")
                graphs_table.add_column("Files")

                for graph_id in repo.list_graphs():
                    graph = repo.metadata

                    # Get graph type
                    graph_type = "Dataset"

                    # Get creation time
                    created = graph.value(graph_id, PROV.generatedAtTime)
                    if created and isinstance(created, Literal):
                        try:
                            # Parse the datetime from the Literal value
                            dt = datetime.fromisoformat(str(created))
                            created_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                        except (ValueError, TypeError):
                            created_str = str(created)
                    else:
                        created_str = "-"

                    # Count distributions (files)
                    file_count = len(
                        list(graph.objects(graph_id, DCAT.distribution))
                    )

                    graphs_table.add_row(
                        graph_id.n3(graph.namespace_manager),
                        graph_type,
                        created_str,
                        str(file_count),
                    )

                console.print(graphs_table)

                # Show the current activity using the lynx renderer
                activity_uri = URIRef(os.environ["BUBBLE_ACTIVITY"])
                with document() as doc:
                    with autoexpanding(3):
                        rdf_resource(activity_uri)
                        print(doc.to_html(compact=False))
                        render_html(doc.element, console)

        except ValueError as e:
            # Handle missing environment variables
            console.print(f"[red]Error:[/] {str(e)}")
            return

    trio_asyncio.run(run)


@app.command()
def img(
    prompt: str,
    repo_path: str = RepoPath,
) -> None:
    """Generate an image using Replicate AI."""
    configure_logging(level=get_log_level())

    async def run_generate_images():
        # Ensure REPLICATE_API_TOKEN is set
        if "REPLICATE_API_TOKEN" not in os.environ:
            console.print(
                "[red]Error:[/] REPLICATE_API_TOKEN environment variable is not set"
            )
            return

        console.print(f"[green]Generating image for prompt:[/] {prompt}")

        # Try to use bubble environment if available
        if "BUBBLE" in os.environ:
            try:
                async with from_env() as repo:
                    await generate_images(repo, prompt)
            except ValueError as e:
                console.print(f"[red]Error:[/] {str(e)}")
                return
        else:
            # Fall back to creating repo from path
            git = Git(trio.Path(repo_path))
            repo = await Repository.create(
                git, namespace=Namespace("file://" + repo_path + "/")
            )
            await repo.load_all()
            await generate_images(repo, prompt)

    async def generate_images(repo: Repository, prompt: str):
        """Generate and save images for the given prompt."""
        try:
            readables = await make_image(prompt)

            for i, readable in enumerate(readables):
                img_data = await readable.aread()
                name = f"{fresh_id()}.webp"

                # Save the image
                blob = await repo.get_file(
                    context.graph.get().identifier, name, "image/webp"
                )
                await blob.write(img_data)
                await repo.save_all()

                console.print(f"[green]Image saved to:[/] {blob.path}")
                await trio.run_process(["open", str(blob.path)])

        except Exception as e:
            console.print(f"[red]Error generating image:[/] {str(e)}")

    trio_asyncio.run(run_generate_images)


if __name__ == "__main__":
    app()
