from typing import Annotated, Optional
import trio
import typer
from typer import Option, Argument
from pathlib import Path
from rich.console import Console
from rich.syntax import Syntax
import subprocess

from rdflib import Graph, Namespace, BNode, URIRef

from bubble.id import Mint
from bubble.n3 import N3Processor

app = typer.Typer()
mint = Mint()
console = Console(width=80)

def print_graph(g: Graph) -> None:
    """Print a graph with syntax highlighting"""
    content = g.serialize(format="n3")
    syntax = Syntax(content, "turtle", theme="coffee", word_wrap=True)
    console.print(syntax)

def handle_output(g: Graph, output_path: Optional[str], message: str) -> None:
    """Handle graph output to file or stdout"""
    content = g.serialize(format="n3")
    if output_path:
        with open(output_path, "w") as f:
            f.write(content)
        console.print(f"\n{message}: {output_path}")
    else:
        print_graph(g)

def handle_error(e: Exception, context: str = "") -> None:
    """Handle and print errors consistently"""
    if isinstance(e, FileNotFoundError):
        console.print(f"[red]Error:[/red] File '{context}' not found")
    elif isinstance(e, subprocess.CalledProcessError):
        console.print(f"[red]EYE reasoner error:[/red]\n{e.stderr}")
    else:
        console.print(f"[red]Error:[/red] {str(e)}")


@app.command()
def fresh(
    namespace: Annotated[
        str, Option(help="Base namespace for the IRI")
    ] = "https://swa.sh/.well-known/genid/",
    casual: Annotated[
        bool, Option(help="Generate a casual IRI (default is secure)")
    ] = False,
) -> None:
    """Generate a unique IRI, either secure (default) or casual."""
    ns = Namespace(namespace)
    if casual:
        iri = mint.fresh_casual_iri(ns)
    else:
        iri = mint.fresh_secure_iri(ns)
    typer.echo(iri)


@app.command()
def show(path: str):
    """Show the contents of an N3 file with syntax highlighting"""
    try:
        processor = N3Processor()
        g = processor.show(path)
        print_graph(g)
    except Exception as e:
        handle_error(e, path)


@app.command()
def skolemize(
    input_path: Annotated[str, Argument(help="Input N3 file path")],
    output_path: Annotated[
        str | None,
        Option(help="Optional output file path (defaults to stdout)"),
    ] = None,
    namespace: Annotated[
        str, Option(help="Base namespace for skolemized IRIs")
    ] = "https://swa.sh/.well-known/genid/",
):
    """Convert blank nodes in an N3 file to fresh IRIs"""
    try:
        processor = N3Processor()
        g = processor.skolemize(input_path, namespace)
        handle_output(g, output_path, "Skolemized graph written to")
    except Exception as e:
        handle_error(e, input_path)


@app.command()
def reason(
    input_path: Annotated[str, Argument(help="Input N3 file path")],
    output_path: Annotated[
        str | None,
        Option(help="Optional output file path (defaults to stdout)"),
    ] = None,
):
    """Run the EYE reasoner on an N3 file"""
    try:
        processor = N3Processor()
        g = trio.run(processor.reason, input_path)
        handle_output(g, output_path, "Reasoning output written to")
    except Exception as e:
        handle_error(e, input_path)


if __name__ == "__main__":
    app()
