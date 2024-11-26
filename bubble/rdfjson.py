from typing import Any, Union

from rdflib import RDF, BNode, Graph, URIRef, Literal, IdentifiedNode
from rdflib.graph import _SubjectType

from bubble.ns import JSON
from bubble.rdfutil import select_rows
from bubble.graphvar import using_graph


def json_from_rdf(graph: Graph, node: _SubjectType) -> dict:
    with using_graph(graph):
        return {
            row.key.toPython(): convert_json_value(graph, row.value)
            for row in select_rows(
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
        return json_from_rdf(graph, value)
    else:
        raise ValueError(f"Unexpected value type: {type(value)}")


def rdf_from_json(graph: Graph, value: dict) -> BNode:
    """Convert a Python dictionary to an RDF JSON object representation.

    Args:
        graph: The RDF graph to add the JSON structure to
        value: The Python dictionary to convert

    Returns:
        A blank node representing the root of the JSON object in RDF
    """

    def convert_value(val: Any) -> Union[BNode, Literal, URIRef]:
        if isinstance(val, dict):
            return rdf_from_json(graph, val)
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
