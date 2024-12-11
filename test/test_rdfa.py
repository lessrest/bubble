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
                rdf_resource(
                    subject.node,
                    {
                        "type": EX.TestType,
                        "predicates": [
                            (RDFS.label, Literal("Test Label")),
                            (EX.property, Literal("Test Value")),
                        ],
                    },
                )

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
                    
                    const parser = new RdfaParser({{
                        baseIRI: 'http://example.org/',
                        contentType: 'text/html'
                    }});

                    const quads = [];
                    parser.on('data', quad => {{
                        quads.push({{
                            subject: quad.subject.value,
                            predicate: quad.predicate.value,
                            object: quad.object.value,
                            graph: quad.graph.value
                        }});
                    }});

                    parser.on('error', console.error);
                    
                    const html = fs.readFileSync('{html_path}', 'utf8');
                    parser.write(html);
                    parser.end();

                    console.log(JSON.stringify(quads));
                    '''
                ], capture_output=True, text=True, check=True)

                # Parse the output quads
                parsed = Graph()
                for quad in json.loads(result.stdout):
                    subject = EX[quad['subject'].split('/')[-1]]
                    predicate = (
                        EX[quad['predicate'].split('/')[-1]] if 'example.org' in quad['predicate']
                        else RDF.type if 'type' in quad['predicate']
                        else RDFS.label if 'label' in quad['predicate']
                        else None
                    )
                    if predicate:
                        parsed.add((
                            subject,
                            predicate,
                            Literal(quad['object'])
                        ))

                # Get default graph from dataset for comparison
                default_graph = Graph()
                for s, p, o in g.default_context:
                    default_graph.add((s, p, o))

                # Check for isomorphism
                assert default_graph.isomorphic(parsed), "Parsed RDFa should match original graph"

            finally:
                html_path.unlink()
