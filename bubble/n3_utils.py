"""Utility functions for N3 processing."""

from typing import Sequence, Optional
from rdflib import Graph, URIRef, BNode, Namespace
import subprocess
from bubble.id import Mint

def print_n3(graph: Graph) -> None:
    """Print the graph in N3 format"""
    from rich import print
    from rich.panel import Panel
    from rich.syntax import Syntax
    
    n3 = graph.serialize(format="n3")
    n3 = n3.replace("    ", "  ")  # Replace 4 spaces with 2 spaces globally
    print(Panel(Syntax(n3, "turtle"), title="N3"))

def get_single_object(graph: Graph, subject, predicate):
    """Get a single object for a subject-predicate pair"""
    objects = list(graph.objects(subject, predicate))
    if len(objects) != 1:
        raise ValueError(f"Expected 1 object, got {len(objects)}")
    return objects[0]

def get_objects(graph: Graph, subject, predicate):
    """Get all objects for a subject-predicate pair"""
    return list(graph.objects(subject, predicate))

def show(input_path: str) -> Graph:
    """Load and normalize an N3 file"""
    g = Graph()
    g.parse(input_path, format="n3")
    return g

async def reason(input_paths: Sequence[str]) -> Graph:
    """Run the EYE reasoner on N3 files and return the resulting graph"""
    cmd = ["eye", "--quiet", "--nope", "--pass", *input_paths]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    
    g = Graph()
    g.parse(data=result.stdout, format="n3")
    return g

def skolemize(
    g: Graph,
    namespace: str = "https://swa.sh/.well-known/genid/",
) -> Graph:
    """Convert blank nodes in a graph to fresh IRIs"""
    mint = Mint()
    ns = Namespace(namespace)
    g_sk = Graph()

    # Copy namespace bindings
    for prefix, namespace in g.namespaces():
        g_sk.bind(prefix, namespace)
    g_sk.bind("id", ns)

    # Create mapping of blank nodes to IRIs
    bnode_map = {}

    def get_iri_for_bnode(bnode):
        if bnode not in bnode_map:
            bnode_map[bnode] = mint.fresh_secure_iri(ns)
        return bnode_map[bnode]

    # Copy all triples, consistently replacing blank nodes
    for s, p, o in g:
        s_new = get_iri_for_bnode(s) if isinstance(s, BNode) else s
        o_new = get_iri_for_bnode(o) if isinstance(o, BNode) else o
        g_sk.add((s_new, p, o_new))

    return g_sk
