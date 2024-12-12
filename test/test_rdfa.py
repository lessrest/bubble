import subprocess
import tempfile
from pathlib import Path

from rdflib import Graph, Namespace
from swash.desc import new_dataset, resource, has, label
from swash.rdfa import autoexpanding, rdf_resource
from swash.html import document, Fragment, root

EX = Namespace("http://example.org/")


def test_rdfa_roundtrip():
    # Create a simple test graph
    with new_dataset() as g:
        with resource(EX.TestType) as subject:
            label("Test Label")
            has(EX.property, "Test Value")

        # Render the graph to HTML with RDFa
        with document():
            with autoexpanding(4):
                rdf_resource(subject.node)

            # Get the rendered HTML
            doc = root.get()
            assert isinstance(doc, Fragment)
            html = doc.to_html()

            print(html)

            # Write HTML to temp file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".html", delete=False
            ) as f:
                f.write(html)
                html_path = Path(f.name)

            try:
                # Parse HTML with RDFa parser
                result = subprocess.run(
                    [
                        "node",
                        "-e",
                        f"""
                    const fs = require('fs');
                    const RdfaParser = require('rdfa-streaming-parser').RdfaParser;
                    const N3 = require('n3');

                    const parser = new RdfaParser({{
                        baseIRI: 'http://example.org/',
                        contentType: 'text/html'
                    }});

                    const writer = new N3.Writer({{format: 'N-Quads'}});

                    parser.on('data', quad => {{
                        writer.addQuad(quad);
                    }});

                    parser.on('error', console.error);

                    const html = fs.readFileSync('{html_path}', 'utf8');
                    parser.write(html);
                    parser.end();

                    writer.end((error, result) => {{
                        if (error) throw error;
                        console.log(result);
                    }});
                    """,
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )

                # Parse the N-Quads output
                parsed = Graph()
                parsed.parse(data=result.stdout, format="nquads")

                # Print both graphs for debugging
                print("\nOriginal graph:")
                print(g.serialize(format="turtle"))
                print("\nParsed RDFa graph:")
                print(parsed.serialize(format="turtle"))

                # Check for isomorphism using rdflib.compare
                from rdflib.compare import isomorphic

                # Get default graph from dataset
                default_graph = Graph()
                for s, p, o in g.default_context:
                    default_graph.add((s, p, o))
                assert isomorphic(
                    default_graph, parsed
                ), "Parsed RDFa should match original graph"

            finally:
                html_path.unlink()
