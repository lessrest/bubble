import typer
from rdflib import Namespace
from bubble.id import Mint

app = typer.Typer()
mint = Mint()

@app.command()
def mint_casual(
    namespace: str = typer.Option(
        "https://swa.sh/",
        "--namespace", "-n",
        help="Base namespace for the IRI"
    )
) -> None:
    """Generate a new casual IRI using XID."""
    ns = Namespace(namespace)
    iri = mint.fresh_casual_iri(ns)
    typer.echo(iri)

if __name__ == "__main__":
    app()
