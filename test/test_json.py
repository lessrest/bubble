import math
import string

import pytest
import hypothesis.strategies as st

from rdflib import XSD, Graph, Literal, Variable
from hypothesis import given

from bubble.json import (
    json_from_rdf,
    rdf_from_json,
)
from bubble.prfx import JSON
from bubble.util import is_a, new, select_rows
from bubble import vars


@pytest.fixture
def graph():
    """Create a test graph with JSON data"""
    with vars.graph.bind(Graph()) as g:
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
    result = json_from_rdf(literal)
    assert result == "test"


def test_convert_json_value_object(graph: Graph):
    assert json_from_rdf(
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
        json_from_rdf(Variable("test"))


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


json = st.recursive(
    st.none() | st.booleans() | st.floats() | st.text(string.printable),
    lambda children: st.lists(children)
    | st.dictionaries(st.text(string.printable), children),
)


@given(json)
def test_json_to_rdf_roundtrip(json_data):
    """Test converting JSON to RDF and back"""
    rdf_data = rdf_from_json(json_data)
    if isinstance(json_data, float) and math.isnan(json_data):
        x = json_from_rdf(rdf_data)
        assert isinstance(x, float)
        assert math.isnan(x)
    else:
        assert json_from_rdf(rdf_data) == json_data


@given(st.integers())
def test_integer_typing(integer: int):
    assert is_a(rdf_from_json(integer), XSD.integer)


@given(st.floats())
def test_float_typing(float: float):
    assert is_a(rdf_from_json(float), XSD.double)