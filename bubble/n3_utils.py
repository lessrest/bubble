"""Utility functions for N3 processing."""

from typing import Sequence
from rdflib import RDF, Graph, IdentifiedNode, Literal, BNode, Namespace
from rdflib.graph import _SubjectType
import subprocess
from bubble.id import Mint
from bubble.ns import JSON


def print_n3(graph: Graph) -> None:
    """Print the graph in N3 format"""
    from rich import print
    from rich.panel import Panel
    from rich.syntax import Syntax

    n3 = graph.serialize(format="n3")
    n3 = n3.replace("    ", "  ")  # Replace 4 spaces with 2 spaces globally
    print(
        Panel(Syntax(n3, "turtle", theme="coffee", word_wrap=True), title="N3")
    )


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


"""Functions for converting between JSON and RDF representations.

The RDF representation uses a custom JSON ontology with the following structure:

    [
        a json:Object ;
        json:has [
            json:property "name" ;
            json:value "John"
        ] ;
        json:has [
            json:property "age" ;
            json:value 30
        ] ;
        json:has [
            json:property "children" ;
            json:value json:null
        ]
    ]
"""


def get_json_value(graph: Graph, node: _SubjectType) -> dict:
    """Convert an RDF JSON object node to a Python dictionary.

    Args:
        graph: The RDF graph containing the JSON structure
        node: The root node of the JSON object to convert

    Returns:
        A Python dictionary representing the JSON structure

    Raises:
        ValueError: If an unexpected value type is encountered
    """
    result = {}
    for prop in get_objects(graph, node, JSON.has):
        key = get_single_object(graph, prop, JSON.key).toPython()
        value = get_single_object(graph, prop, JSON.val)
        # if value is a literal, add it to the result
        if isinstance(value, Literal):
            result[key] = value.toPython()
        elif isinstance(value, IdentifiedNode):
            if value.toPython() == JSON.null:
                result[key] = None
            else:
                result[key] = get_json_value(graph, value)
        else:
            raise ValueError(f"Unexpected value type: {type(value)}")
    return result


def json_to_n3(graph: Graph, value: dict) -> BNode:
    """Convert a Python dictionary to an RDF JSON object representation.

    Args:
        graph: The RDF graph to add the JSON structure to
        value: The Python dictionary to convert

    Returns:
        A blank node representing the root of the JSON object in RDF
    """
    bn = BNode()
    graph.add((bn, RDF.type, JSON.Object))
    for key, value in value.items():
        prop = BNode()
        graph.add((bn, JSON["has"], prop))
        graph.add((prop, JSON["key"], Literal(key)))
        if isinstance(value, dict):
            graph.add((prop, JSON["val"], json_to_n3(graph, value)))
        elif value is None:
            graph.add((prop, JSON["val"], JSON.null))
        else:
            graph.add((prop, JSON["val"], Literal(value)))
    return bn
