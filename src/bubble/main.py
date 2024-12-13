import pathlib
import os

from datetime import UTC, datetime
from urllib.parse import urlparse

from fastapi import FastAPI
import swash
from swash import html
import trio
import typer
import hypercorn
import hypercorn.trio

from typer import Option
from rdflib import Literal, URIRef, Namespace, PROV, DCAT
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

import swash.vars as vars

from swash.prfx import NT
from swash.util import add
from bubble.data import Git, Repository
from bubble.mesh import SimpleSupervisor, spawn, txgraph
from bubble.chat import BubbleChat
from bubble.cred import get_anthropic_credential
from bubble.logs import configure_logging
from bubble.repo import loading_bubble_from
from bubble.slop import Claude
from bubble.stat.stat import gather_system_info
from bubble.town import (
    Site,
)
from bubble.mesh import UptimeActor
from bubble.deepgram.talk import DeepgramClientActor
from swash.lynx import render_html
from swash.rdfa import autoexpanding, rdf_resource

logger = configure_logging()

console = Console(width=80)

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
)

home = pathlib.Path.home()

BubblePath = Option(str(home / "bubble"), "--bubble", help="Bubble path")
RepoPath = Option(str(home / "repo"), "--repo", help="Repository path")


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
def shell(
    repo_path: str = RepoPath,
    namespace: str = Option(
        "https://example.com/", "--namespace", help="Namespace"
    ),
) -> None:
    """Create a new repository and start a shell session."""

    configure_logging()

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
                # Start a new shell session activity
                with repo.new_activity(
                    NT.InteractiveShellSession
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
                town = Site(base_url, bind, repo)
                with town.install_context():
                    # Create and persist the town's identity
                    async with txgraph():
                        town.vat.create_identity_graph()

                    supervisor = await spawn(
                        nursery,
                        SimpleSupervisor(
                            DeepgramClientActor("Deepgram Client")
                        ),
                    )

                    # Link supervisor to the town's identity
                    async with txgraph():
                        town.vat.link_actor_to_identity(supervisor)

                    uptime = await spawn(
                        nursery,
                        UptimeActor(datetime.now(UTC)),
                        name="uptime",
                    )

                    # Link uptime actor to the town's identity
                    async with txgraph():
                        town.vat.link_actor_to_identity(uptime)

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
        return r"\[\e[1m\][\[\e[34m\]town\[\e[0m\]\[\e[1m\]]\[\e[0m\] $ "

    trio.run(run)


@app.command()
def info() -> None:
    """Display information about the current bubble environment and graphs."""
    console = Console(width=78)

    # Get environment variables
    bubble_path = os.environ.get("BUBBLE")
    bubble_graph = os.environ.get("BUBBLE_GRAPH")
    bubble_graph_dir = os.environ.get("BUBBLE_GRAPH_DIR")
    bubble_activity = os.environ.get("BUBBLE_ACTIVITY")
    bubble_agent = os.environ.get("BUBBLE_AGENT")

    assert bubble_graph
    assert bubble_graph_dir
    assert bubble_activity
    assert bubble_agent

    # If no bubble environment variables are set
    if not bubble_path:
        console.print(
            Panel(
                "No bubble environment detected. Use [bold]bubble shell[/] to create one.",
                title="Bubble Status",
                border_style="yellow",
            )
        )
        return

    async def show_info():
        # Load the repository
        git = Git(trio.Path(bubble_path))
        repo = await Repository.create(
            git, namespace=Namespace("file://" + bubble_path + "/")
        )
        await repo.load_all()

        # Create environment info table
        env_table = Table(box=box.ROUNDED, title="Environment")
        env_table.add_column("Key", style="bold blue")
        env_table.add_column("Value")

        env_table.add_row("Bubble Path", bubble_path)
        if bubble_graph:
            env_table.add_row("Current Graph", bubble_graph)
        if bubble_graph_dir:
            env_table.add_row("Graph Directory", bubble_graph_dir)

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
        activity_uri = URIRef(bubble_activity)
        with html.document() as doc:
            with swash.vars.dataset.bind(repo.dataset):
                rdf_resource(activity_uri)
                #                from pudb import set_trace

                #               set_trace()
                render_html(doc.element, console)

        # Show the current agent using the lynx renderer
        agent_uri = URIRef(bubble_agent)
        with html.document() as doc:
            with swash.vars.dataset.bind(repo.dataset):
                rdf_resource(agent_uri)
                render_html(doc.element, console)

        # Show the current graph using the lynx renderer
        graph_uri = URIRef(bubble_graph)
        with html.document() as doc:
            with swash.vars.dataset.bind(repo.dataset):
                with autoexpanding(4):
                    rdf_resource(graph_uri)
                #                print(doc.to_html(compact=False))
                render_html(doc.element, console)

    trio.run(show_info)


if __name__ == "__main__":
    app()
