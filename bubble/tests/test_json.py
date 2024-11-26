import pytest

from rdflib import Graph, Literal, Variable

from bubble.vars import using_graph
from bubble.prfx import JSON
from bubble.json import (
    rdf_from_json,
    json_from_rdf,
    convert_json_value,
)
from bubble.util import new, select_rows


@pytest.fixture
def graph():
    """Create a test graph with JSON data"""
    with using_graph(Graph()) as g:
        g.bind("json", JSON)
        yield g


def test_get_json_value(graph: Graph):
    assert json_from_rdf(
        new(
            JSON.Object,
            {
                JSON.has: new(
                    None,
                    {
                        JSON.key: Literal("test_key"),
                        JSON.val: Literal("test_value"),
                    },
                )
            },
        ),
    ) == {"test_key": "test_value"}


def test_convert_json_value_literal():
    literal = Literal("test")
    result = convert_json_value(literal)
    assert result == "test"


def test_convert_json_value_object(graph: Graph):
    assert convert_json_value(
        new(
            JSON.Object,
            {
                JSON.has: new(
                    None,
                    {
                        JSON.key: Literal("nested"),
                        JSON.val: Literal("value"),
                    },
                )
            },
        ),
    ) == {"nested": "value"}


def test_convert_json_value_invalid():
    """Test handling invalid value types"""
    with pytest.raises(ValueError):
        convert_json_value(Variable("test"))


def test_json_to_n3_simple(graph):
    """Test converting simple Python dict to RDF"""
    root = rdf_from_json({"key": "value"})
    rows = select_rows(
        """
        SELECT ?key ?value
        WHERE { ?root json:has [ json:key ?key ; json:val ?value ] }
        """,
        {"root": root},
    )
    assert rows == [(Literal("key"), Literal("value"))]


def test_json_to_n3_nested():
    """Test converting nested dict structures"""
    root = rdf_from_json({"outer": {"inner": "value"}})
    rows = select_rows(
        """
        SELECT ?outer_key ?inner_key ?inner_value WHERE {
            ?root json:has ?outer_prop .
            ?outer_prop json:key ?outer_key ;
                       json:val ?inner_obj .
            ?inner_obj a json:Object ;
                      json:has ?inner_prop .
            ?inner_prop json:key ?inner_key ;
                        json:val ?inner_value .
        }
        """,
        {"root": root},
    )

    assert len(rows) == 1
    assert rows[0] == (
        Literal("outer"),
        Literal("inner"),
        Literal("value"),
    )


def test_json_to_n3_null():
    """Test handling null values"""
    root = rdf_from_json({"key": None})
    rows = select_rows(
        """
        SELECT ?key ?value
        WHERE { ?root json:has [ json:key ?key ; json:val ?value ] }
        """,
        {"root": root},
    )
    assert rows == [(Literal("key"), JSON.null)]
