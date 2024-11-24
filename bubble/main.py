from typing import Annotated
import typer
from pathlib import Path

from rdflib import Graph, Namespace

from bubble.id import Mint

app = typer.Typer()
mint = Mint()


@app.command()
def fresh(
    namespace: Annotated[
        str,
        typer.Option(
            "--namespace",
            "-n",
            help="Base namespace for the IRI",
        ),
    ] = "https://swa.sh/",
    casual: Annotated[
        bool,
        typer.Option(
            help="Generate a casual IRI (default is secure)",
        ),
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
def show(
    file: Annotated[
        Path,
        typer.Argument(
            help="N3 file to display",
            exists=True,
            dir_okay=False,
            readable=True,
        ),
    ]
) -> None:
    """Load and display an N3 file."""
    g = Graph()
    g.parse(file, format="n3") 
    print(g.serialize(format="n3"))

if __name__ == "__main__":
    app()
