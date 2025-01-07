import tempfile
import subprocess

from pathlib import Path

from rdflib import RDFS, Graph, Dataset, Literal, Namespace

from swash import here as swash_vars
from swash.html import Fragment, tag, root, text, document
from swash.rdfa import rdf_resource, autoexpanding
from swash.util import new
from bubble.repo.repo import context

EX = Namespace("http://example.org/")


def test_rdfa_roundtrip():
    # Create a simple test graph
    dataset = Dataset()
    g = dataset.default_context
    g.base = str(EX)
    with context.buffer.bind(g):
        subject = new(
            EX.TestType,
            {
                RDFS.label: Literal("Test Label"),
                EX.property: Literal("Test Value"),
            },
        )

        # Render the graph to HTML with RDFa
        with document():
            with tag("html"):
                with tag("head"):
                    with tag("title"):
                        text("Test Title")
                with tag("body"):
                    with swash_vars.dataset.bind(dataset):
                        with autoexpanding(0):
                            rdf_resource(subject)

            # Get the rendered HTML
            doc = root.get()
            assert isinstance(doc, Fragment)
            html = doc.to_html(compact=True)

            print(html)

            # Parse HTML with RDFa parser
            result = parse_rdfa_to_nquads(html)
            print("RDFa parser result:")
            print(result.stdout)
            print(result.stderr)

            # Parse the N-Quads output
            parsed = Graph()
            parsed.parse(data=result.stdout, format="nquads")

            # Print both graphs for debugging
            print("\nOriginal graph:")
            print(g)
            print(g.serialize(format="n3"))
            print("\nParsed RDFa graph:")
            print(parsed.serialize(format="turtle"))

            # Check for isomorphism using rdflib.compare
            from rdflib.compare import isomorphic

            assert isomorphic(
                g, parsed
            ), "Parsed RDFa should match original graph"


def parse_rdfa_to_nquads(html):
    # Write HTML to temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False
    ) as f:
        f.write(html)
        html_path = Path(f.name)

        return subprocess.run(
            [
                "node",
                str(Path(__file__).parent / "js" / "rdfa_parser.js"),
                str(html_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
