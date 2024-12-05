import capnp
from rich import print

# Load the Cap'n Proto schema
schema = capnp.load("src/proto/dom.capnp")


def test_load_schema():
    """Test that we can load and access the schema interfaces"""
    # Print schema information for inspection
    print("Schema:", schema)
    print("DOMNode:", schema.DOMNode)
    print("DOMNode schema:", schema.DOMNode.schema)
    print("DOMNode methods:", list(schema.DOMNode.schema.methods))
    print("DOMDocument methods:", list(schema.DOMDocument.schema.methods))
    print("DOMSession methods:", list(schema.DOMSession.schema.methods))

    # Verify we can access the interfaces
    assert hasattr(schema, "DOMNode")
    assert hasattr(schema, "DOMDocument")
    assert hasattr(schema, "DOMSession")

    # Verify we can access the methods
    node_methods = list(schema.DOMNode.schema.methods)
    assert len(node_methods) == 3  # append, prepend, replace

    doc_methods = list(schema.DOMDocument.schema.methods)
    assert len(doc_methods) == 1  # createElement

    session_methods = list(schema.DOMSession.schema.methods)
    assert len(session_methods) == 3  # subscribe, unsubscribe, getDocument
