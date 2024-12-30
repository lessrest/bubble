from rdflib import Graph, Namespace

from swash.util import S
from bubble.mesh.base import vat


def is_did_key(graph: Graph, node: S) -> bool:
    """Check if a node is a DID key."""
    return node in Namespace("did:")


def is_current_identity(node: S) -> bool:
    """Check if a node is the current town's identity."""
    try:
        return node == vat.get().identity_uri
    except Exception:
        return False


def get_node_classes(graph: Graph, node: S) -> str:
    """Get the CSS classes for a node based on its type and identity status."""
    is_key = is_did_key(graph, node)
    is_current = is_current_identity(node)

    classes = "pl-2 "
    if is_key:
        if not is_current:
            classes += "opacity-50 hidden"

    return classes
