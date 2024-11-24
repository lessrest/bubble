from typing import Annotated
import typer

from rdflib import Namespace

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
    secure: Annotated[
        bool,
        typer.Option(
            help="Generate a secure IRI",
        ),
    ] = False,
) -> None:
    """Generate a unique IRI, either secure or casual (the default)."""
    ns = Namespace(namespace)
    if secure:
        iri = mint.fresh_secure_iri(ns)
    else:
        iri = mint.fresh_casual_iri(ns)
    typer.echo(iri)


if __name__ == "__main__":
    app()
