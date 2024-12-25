"""Initialize a new Bubble configuration."""

import os

from typing import Optional
from pathlib import Path

import trio
import typer
import structlog

from rdflib import Graph, URIRef, Literal, Namespace
from rich.prompt import Prompt, Confirm
from rich.console import Console
from rdflib.namespace import RDF, XSD

from bubble.cli.app import RepoPath, app
from bubble.http.cert import generate_self_signed_cert

# Define our configuration namespace
CONFIG = Namespace("https://bubble.node.town/vocab/config#")

logger = structlog.get_logger()
console = Console()
app_dir = Path(typer.get_app_dir("bubble"))


@app.command()
def init(
    repo_path: str = RepoPath,
) -> None:
    """Initialize a new Bubble configuration through an interactive process."""
    trio.run(_bubble_init, repo_path)


async def _bubble_init(repo_path: str) -> None:
    """Run the interactive configuration process."""
    config_path = app_dir / "config.ttl"

    if config_path.exists():
        if not Confirm.ask(
            f"Configuration file already exists at {config_path}. Overwrite?"
        ):
            return

    # Create a new RDF graph for configuration
    g = Graph()
    g.bind("config", CONFIG)

    # Create the main configuration node
    config = URIRef("bubble:config")
    g.add((config, RDF.type, CONFIG.Configuration))

    # Server configuration
    cert_file = None
    key_file = None
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

        g.add((config, CONFIG.serverType, Literal("self-signed")))
        g.add((config, CONFIG.hostname, Literal(hostname)))
        g.add((config, CONFIG.port, Literal(port, datatype=XSD.integer)))
        g.add((config, CONFIG.certFile, Literal(str(cert_file))))
        g.add((config, CONFIG.keyFile, Literal(str(key_file))))

        base_url = f"https://{hostname}:{port}/"

    elif server_type == "ssl":
        hostname = Prompt.ask("Enter hostname")
        port = Prompt.ask("Enter port", default="443")
        cert_file = Prompt.ask("Path to SSL certificate file")
        key_file = Prompt.ask("Path to SSL private key file")

        g.add((config, CONFIG.serverType, Literal("ssl")))
        g.add((config, CONFIG.hostname, Literal(hostname)))
        g.add((config, CONFIG.port, Literal(port, datatype=XSD.integer)))
        g.add((config, CONFIG.certFile, Literal(cert_file)))
        g.add((config, CONFIG.keyFile, Literal(key_file)))

        base_url = f"https://{hostname}:{port}/"

    else:  # http with reverse proxy
        bind_host = Prompt.ask("Enter bind address", default="127.0.0.1")
        bind_port = Prompt.ask("Enter bind port", default="2026")
        base_url = Prompt.ask(
            "Enter public base URL (including scheme and path)",
            default="https://example.com/",
        )

        g.add((config, CONFIG.serverType, Literal("http")))
        g.add((config, CONFIG.bindHost, Literal(bind_host)))
        g.add(
            (
                config,
                CONFIG.bindPort,
                Literal(bind_port, datatype=XSD.integer),
            )
        )

    g.add((config, CONFIG.baseUrl, Literal(base_url)))
    g.add((config, CONFIG.repoPath, Literal(str(repo_path))))

    # Save the configuration
    os.makedirs(app_dir, exist_ok=True)
    g.serialize(config_path, format="turtle")
    console.print(f"[green]Configuration saved to {config_path}[/]")

    # Set environment variables for immediate use
    os.environ["BUBBLE"] = str(repo_path)
    os.environ["BUBBLE_BASE"] = base_url

    if server_type in ["self-signed", "ssl"]:
        os.environ["BUBBLE_CERT"] = str(cert_file)
        os.environ["BUBBLE_KEY"] = str(key_file)

    console.print("\n[bold]Next steps:[/]")
    console.print("1. Review the generated config.ttl file")
    console.print("2. Run 'bubble serve' to start the server")
    console.print("3. Visit your Bubble at", base_url)
