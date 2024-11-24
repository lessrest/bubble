from typing import Annotated
import typer

from rdflib import Namespace

from bubble.id import Mint

app = typer.Typer()
mint = Mint()


@app.command("fresh")
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


if __name__ == "__main__":
    app()
