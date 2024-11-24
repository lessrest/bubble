import os
from typing import Optional
import trio
import typer
from typer import Option
from pathlib import Path
from rich.console import Console
from rich.syntax import Syntax
import subprocess

from rdflib import Graph

from bubble.n3 import N3Processor

DEFAULT_N3_PATH = os.environ.get("BUBBLE_N3_PATH", "./rules/inbox.n3")
console = Console(width=80)

app = typer.Typer(add_completion=False)

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
def main(
    input_path: str = Option(DEFAULT_N3_PATH, "--input", "-i", help="Input N3 file path"),
    output_path: Optional[str] = Option(None, "--output", "-o", help="Output file path (defaults to stdout)"),
    reason: bool = Option(False, "--reason", "-r", help="Run the EYE reasoner on the input"),
    skolem: bool = Option(False, "--skolem", "-s", help="Convert blank nodes to IRIs"),
    namespace: str = Option(
        "https://swa.sh/.well-known/genid/",
        "--namespace", "-n",
        help="Base namespace for skolemized IRIs"
    ),
) -> None:
    """Process N3 files with optional reasoning and skolemization."""
    try:
        processor = N3Processor()
        
        # Load the input graph
        g = processor.show(input_path)
        
        # Apply reasoning if requested
        if reason:
            g = trio.run(processor.reason, input_path)
            
        # Apply skolemization if requested
        if skolem:
            g = processor.skolemize(input_path, namespace)
            
        # Output the result
        handle_output(g, output_path, "Output written to")
            
    except Exception as e:
        handle_error(e, input_path)


if __name__ == "__main__":
    app()
