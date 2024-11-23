import typer

from rdflib import Namespace

from bubble.id import Mint

app = typer.Typer()
mint = Mint()


@app.command()
def fresh(
    namespace: str = typer.Option(
        "https://swa.sh/",
        "--namespace",
        "-n",
        help="Base namespace for the IRI",
    ),
    secure: bool = typer.Option(
        False, "--secure", help="Generate a secure IRI"
    ),
) -> None:
    """Generate a new IRI using XID."""
    ns = Namespace(namespace)
    if secure:
        iri = mint.fresh_secure_iri(ns)
    else:
        iri = mint.fresh_casual_iri(ns)
    typer.echo(iri)


if __name__ == "__main__":
    app()
