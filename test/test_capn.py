import capnp

# Load the Cap'n Proto schema
dom_capnp = capnp.load("src/proto/dom.capnp")


def test_load_schema():
    """Test that we can load and access the schema interfaces"""
    # Verify we can access the interfaces
    assert hasattr(dom_capnp, "DOMNode")
    assert hasattr(dom_capnp, "DOMDocument")
    assert hasattr(dom_capnp, "DOMSession")

    # Verify the methods exist on DOMNode
    assert hasattr(dom_capnp.DOMNode.schema.fields, "append")
    assert hasattr(dom_capnp.DOMNode.schema.fields, "prepend")
    assert hasattr(dom_capnp.DOMNode.schema.fields, "replace")

    # Verify DOMDocument methods
    assert hasattr(dom_capnp.DOMDocument.schema.fields, "createElement")

    # Verify DOMSession methods
    assert hasattr(dom_capnp.DOMSession.schema.fields, "subscribe")
    assert hasattr(dom_capnp.DOMSession.schema.fields, "unsubscribe")
    assert hasattr(dom_capnp.DOMSession.schema.fields, "getDocument")
