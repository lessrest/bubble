from bubble.n3_utils import get_objects, get_single_object, select_rows
from bubble.ns import JSON
from rdflib.graph import _SubjectType
from typing import Any, Union

from rdflib import RDF, BNode, Graph, IdentifiedNode, Literal, URIRef


def get_json_value(graph: Graph, node: _SubjectType) -> dict:
    return {
        row.key.toPython(): convert_json_value(graph, row.value)
        for row in select_rows(
            graph,
            """
            SELECT ?key ?value WHERE {
                ?node json:has ?prop .
                ?prop json:key ?key .
                ?prop json:val ?value .
            }
            """,
            {"node": node},
        )
    }


def convert_json_value(graph: Graph, value: _SubjectType) -> str | dict:
    if isinstance(value, Literal):
        return value.toPython()
    elif isinstance(value, IdentifiedNode):
        return get_json_value(graph, value)
    else:
        raise ValueError(f"Unexpected value type: {type(value)}")


def json_to_n3(graph: Graph, value: dict) -> BNode:
    """Convert a Python dictionary to an RDF JSON object representation.

    Args:
        graph: The RDF graph to add the JSON structure to
        value: The Python dictionary to convert

    Returns:
        A blank node representing the root of the JSON object in RDF
    """

    def convert_value(val: Any) -> Union[BNode, Literal, URIRef]:
        if isinstance(val, dict):
            return json_to_n3(graph, val)
        elif val is None:
            return JSON.null
        else:
            return Literal(val)

    root = BNode()
    graph.add((root, RDF.type, JSON.Object))

    for key, val in value.items():
        property_node = BNode()
        graph.add((root, JSON["has"], property_node))
        graph.add((property_node, JSON["key"], Literal(key)))
        graph.add((property_node, JSON["val"], convert_value(val)))

    return root
