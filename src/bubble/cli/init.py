"""Initialize a new Bubble configuration."""

import os

from pathlib import Path

import trio
import typer
import structlog

from rdflib import Graph, Literal, Namespace
from rich.prompt import Prompt, Confirm
from rich.console import Console
from rdflib.namespace import RDF, XSD

from swash.mint import fresh_uri
from swash.prfx import BUBBLE
from bubble.cli.app import RepoPath, app
from bubble.http.cert import generate_self_signed_cert

logger = structlog.get_logger()
console = Console()
app_dir = Path(typer.get_app_dir("bubble"))
config_dir = app_dir / "config"


@app.command()
def init(
    repo_path: str = RepoPath,
) -> None:
    """Initialize a new Bubble configuration through an interactive process."""
    trio.run(_bubble_init, repo_path)


async def _bubble_init(repo_path: str) -> None:
    """Run the interactive configuration process."""
    os.makedirs(config_dir, exist_ok=True)
    config_path = config_dir / "server.ttl"

    if config_path.exists():
        if not Confirm.ask(
            f"Configuration file already exists at {config_path}. Overwrite?"
        ):
            return

    # Create a new RDF graph for configuration
    g = Graph()
    g.bind("bubble", BUBBLE)

    # Server configuration
    cert_file = None
    key_file = None
    hostname = None
    port = None
    bind_host = None
    bind_port = None
    base_url = None

    server_type = Prompt.ask(
        "Choose server configuration",
        choices=["self-signed", "ssl", "http"],
        default="self-signed",
    )

    if server_type == "self-signed":
        hostname = Prompt.ask("Enter hostname", default="localhost")
        port = Prompt.ask("Enter port", default="2026")

        # Generate self-signed certificates
        cert_file, key_file = generate_self_signed_cert(hostname)
        base_url = f"https://{hostname}:{port}/"

    elif server_type == "ssl":
        hostname = Prompt.ask("Enter hostname")
        port = Prompt.ask("Enter port", default="443")
        cert_file = Prompt.ask("Path to SSL certificate file")
        key_file = Prompt.ask("Path to SSL private key file")
        base_url = f"https://{hostname}:{port}/"

    else:  # http with reverse proxy
        bind_host = Prompt.ask("Enter bind address", default="127.0.0.1")
        bind_port = Prompt.ask("Enter bind port", default="2026")
        base_url = Prompt.ask(
            "Enter public base URL (including scheme and path)",
            default="https://example.com/",
        )

    # Create the main configuration node with base URL as namespace
    config = fresh_uri(Namespace(base_url))
    g.add((config, RDF.type, BUBBLE.ServerConfiguration))

    # Add server configuration
    g.add((config, BUBBLE.serverType, Literal(server_type)))
    g.add((config, BUBBLE.baseUrl, Literal(base_url)))
    g.add((config, BUBBLE.repoPath, Literal(str(repo_path))))

    if server_type == "self-signed":
        g.add((config, BUBBLE.hostname, Literal(hostname)))
        g.add((config, BUBBLE.port, Literal(port, datatype=XSD.integer)))
        g.add((config, BUBBLE.certFile, Literal(str(cert_file))))
        g.add((config, BUBBLE.keyFile, Literal(str(key_file))))
    elif server_type == "ssl":
        g.add((config, BUBBLE.hostname, Literal(hostname)))
        g.add((config, BUBBLE.port, Literal(port, datatype=XSD.integer)))
        g.add((config, BUBBLE.certFile, Literal(cert_file)))
        g.add((config, BUBBLE.keyFile, Literal(key_file)))
    else:  # http
        g.add((config, BUBBLE.bindHost, Literal(bind_host)))
        g.add(
            (
                config,
                BUBBLE.bindPort,
                Literal(bind_port, datatype=XSD.integer),
            )
        )

    # Optional NATS configuration
    if Confirm.ask("Configure NATS server?", default=False):
        nats_url = Prompt.ask(
            "Enter NATS server URL", default="nats://localhost:4222"
        )
        g.add((config, BUBBLE.natsUrl, Literal(nats_url)))

    # Save the configuration
    g.serialize(config_path, format="turtle")
    console.print(f"[green]Configuration saved to {config_path}[/]")

    # Set environment variables for immediate use
    os.environ["BUBBLE"] = str(repo_path)
    os.environ["BUBBLE_BASE"] = base_url

    if server_type in ["self-signed", "ssl"]:
        os.environ["BUBBLE_CERT"] = str(cert_file)
        os.environ["BUBBLE_KEY"] = str(key_file)

    console.print("\n[bold]Next steps:[/]")
    console.print("1. Review the generated server.ttl file")
    console.print("2. Run 'bubble serve' to start the server")
    console.print("3. Visit your Bubble at", base_url)
