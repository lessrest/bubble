"""Utility functions for N3 processing."""

from typing import Sequence
from rdflib import RDF, Graph, IdentifiedNode, Literal, BNode, Namespace
from rdflib.graph import _SubjectType
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


# we represent json in rdf using the nt:JSONObject class
# # example:
# # nt:posts [
#            a nt:JSONObject ;
#            nt:hasProperty [
#                a nt:Property ;
#                nt:key "input" ;
#                nt:value [
#                    a nt:JSONObject ;
#                    nt:hasProperty [
#                        a nt:Property ;
#                        nt:key "prompt" ;
#                        nt:value ?content
#                    ] ;
#                    nt:hasProperty [
#                        a nt:Property ;
#                        nt:key "size" ;
#                        nt:value ?size
#                    ] ;
#                    nt:hasProperty [
#                        a nt:Property ;
#                        nt:key "style" ;
#                        nt:value ?style
#                    ]
#                ]
#            ]
# we need to recursively convert these to python values
def get_json_value(graph: Graph, node: _SubjectType) -> dict:
    nodetype = get_single_object(graph, node, RDF.type)
    from bubble.NT import NT

    if nodetype != NT.JSONObject:
        raise ValueError(f"Expected nt:JSONObject, got {nodetype}")

    result = {}
    for prop in get_objects(graph, node, NT.hasProperty):
        key = get_single_object(graph, prop, NT.key).toPython()
        value = get_single_object(graph, prop, NT.value)
        # if value is a literal, add it to the result
        if isinstance(value, Literal):
            result[key] = value.toPython()
        elif isinstance(value, IdentifiedNode):
            result[key] = get_json_value(graph, value)
        else:
            raise ValueError(f"Unexpected value type: {type(value)}")
    return result


def json_to_n3(graph: Graph, value: dict) -> BNode:
    """Convert a python dictionary to an N3 graph"""
    from bubble.NT import NT

    bn = BNode()
    graph.add((bn, RDF.type, NT.JSONObject))
    for key, value in value.items():
        prop = BNode()
        graph.add((bn, NT.hasProperty, prop))
        graph.add((prop, NT.key, Literal(key)))
        if isinstance(value, dict):
            graph.add((prop, NT.value, json_to_n3(graph, value)))
        else:
            graph.add((prop, NT.value, Literal(value)))
    return bn
