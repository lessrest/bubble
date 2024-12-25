from typing import List
from collections import defaultdict

from rdflib import Graph, URIRef

from swash.util import S


def count_outbound_links(graph: Graph, node: S) -> int:
    """Count outbound links from a node, excluding rdf:type."""
    return len(list(graph.triples((node, None, None))))


def count_inbound_links(graph: Graph, node: S) -> int:
    """Count inbound links to a node."""
    return len(list(graph.subjects(None, node)))


def get_traversal_order(graph: Graph) -> List[S]:
    """Get nodes in traversal order - prioritizing resources with fewer inbound links and more outbound links."""
    # Count inbound and outbound links for each subject
    link_scores = {}
    for subject in graph.subjects():
        inbound = count_inbound_links(graph, subject)
        outbound = count_outbound_links(graph, subject)
        link_scores[subject] = outbound / 2 - inbound * 2

    # Group nodes by type (URIRef vs BNode)
    typed_nodes = defaultdict(list)
    for node in link_scores:
        if isinstance(node, URIRef):
            typed_nodes["uri"].append(node)
        else:
            typed_nodes["bnode"].append(node)

    # Sort each group by score (descending)
    sorted_nodes = []

    # URIRefs first, sorted by score
    sorted_nodes.extend(
        sorted(
            typed_nodes["uri"], key=lambda x: link_scores[x], reverse=True
        )
    )

    # Then BNodes, sorted by score
    sorted_nodes.extend(
        sorted(
            typed_nodes["bnode"], key=lambda x: link_scores[x], reverse=True
        )
    )

    return sorted_nodes
