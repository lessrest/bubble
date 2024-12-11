import json
import subprocess
import tempfile
from pathlib import Path

from rdflib import Graph, Literal, Namespace, RDF
from rdflib.namespace import RDFS
from swash.desc import new_dataset, resource, property, label
from swash.rdfa import autoexpanding, rdf_resource
from swash.html import document, Fragment, root

EX = Namespace("http://example.org/")


def test_rdfa_roundtrip():
    # Create a simple test graph
    with new_dataset() as g:
        with resource(EX.TestType) as subject:
            label("Test Label")
            property(EX.property, "Test Value")

        # Render the graph to HTML with RDFa
        with document():
            with autoexpanding(4):
                rdf_resource(subject.node)

            # Get the rendered HTML
            doc = root.get()
            assert isinstance(doc, Fragment)
            html = doc.to_html()

            # Write HTML to temp file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
                f.write(html)
                html_path = Path(f.name)

            try:
                # Parse HTML with RDFa parser
                result = subprocess.run([
                    'node', '-e',
                    f'''
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
                    '''
                ], capture_output=True, text=True, check=True)

                # Parse the N-Quads output
                parsed = Graph()
                parsed.parse(data=result.stdout, format='nquads')

                # Get default graph from dataset for comparison
                default_graph = Graph()
                for s, p, o in g.default_context:
                    default_graph.add((s, p, o))

                # Print both graphs for debugging
                print("\nOriginal graph:")
                print(default_graph.serialize(format='turtle'))
                print("\nParsed RDFa graph:")
                print(parsed.serialize(format='turtle'))

                # Check for isomorphism
                assert default_graph.isomorphic(parsed), "Parsed RDFa should match original graph"

            finally:
                html_path.unlink()
