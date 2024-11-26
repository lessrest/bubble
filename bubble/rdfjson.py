from typing import Any

from rdflib import Literal, IdentifiedNode
from rdflib.graph import _SubjectType

from bubble.ns import JSON
from bubble.rdfutil import O, S, new, select_rows


def json_from_rdf(node: _SubjectType) -> dict:
    return {
        row.key.toPython(): convert_json_value(row.value)
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


def convert_json_value(value: _SubjectType) -> str | dict:
    if isinstance(value, Literal):
        return value.toPython()
    elif isinstance(value, IdentifiedNode):
        return json_from_rdf(value)
    else:
        raise ValueError(f"Unexpected value type: {type(value)}")


def rdf_from_json(value: dict) -> S:
    """Convert a Python dictionary to an RDF JSON object representation.

    Args:
        value: The Python dictionary to convert

    Returns:
        A blank node representing the root of the JSON object in RDF
    """

    def convert_value(val: Any) -> O:
        if isinstance(val, dict):
            return rdf_from_json(val)
        elif val is None:
            return JSON.null
        else:
            return Literal(val)

    props = []
    for key, val in value.items():
        prop = new(
            JSON.Property, {JSON.key: key, JSON.val: convert_value(val)}
        )
        props.append(prop)

    return new(JSON.Object, {JSON.has: props})
