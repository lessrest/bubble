from rdflib import Graph, Literal, Namespace
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

            # Parse the HTML back to a graph
            parsed = Graph()
            parsed.parse(data=html, format="html")

            # Check for isomorphism
            assert g.isomorphic(
                parsed
            ), "Parsed RDFa should match original graph"
