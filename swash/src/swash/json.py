from rdflib import IdentifiedNode, Literal, URIRef
from rdflib.collection import Collection
import structlog
from swash.mint import fresh_uri
from swash.prfx import JSON, SWA
from swash.util import O, S, is_a, new, select_rows
from swash import vars
# import importhook

logger = structlog.get_logger()

# logger.info("registering import hook")


# @importhook.on_import("aiohttp")  # type: ignore
# def on_aiohttp_import(aiohttp):
#     # This is a hack to avoid PyLD crashing on load in IPython.
#     raise ImportError("hehe")


try:
    import pyld  # noqa: F401
finally:
    pass


def json_from_rdf(
    node: O,
) -> dict | list | str | bool | int | float | None:
    if node == JSON.null:
        return None

    if isinstance(node, Literal):
        return node.toPython()

    if is_a(node, JSON.Array):
        assert isinstance(node, IdentifiedNode)
        list = Collection(vars.graph.get(), node)
        return [json_from_rdf(item) for item in list]
    if is_a(node, JSON.Object):
        return {
            row.key.toPython(): json_from_rdf(row.value)
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


logger = structlog.get_logger()


def rdf_from_json(
    value: dict | None | str | bool | int | float | list,
) -> S:
    """Convert a Python dictionary to an RDF JSON object representation.

    Args:
        value: The Python dictionary to convert

    Returns:
        A blank node representing the root of the JSON object in RDF
    """

    if value is None:
        return JSON.null
    elif isinstance(value, dict):
        props = []
        for key, val in value.items():
            prop = new(
                JSON.Property,
                {JSON.key: key, JSON.val: rdf_from_json(val)},
            )
            props.append(prop)

        return new(JSON.Object, {JSON.has: props})
    elif isinstance(value, list):
        items = []
        for item in value:
            items.append(rdf_from_json(item))

        collection = Collection(vars.graph.get(), fresh_uri(SWA), items)
        assert isinstance(collection.uri, URIRef)

        return new(JSON.Array, {}, subject=collection.uri)
    else:
        return Literal(value)
