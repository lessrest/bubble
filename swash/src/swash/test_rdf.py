from rdflib import SKOS, URIRef, Literal
from rdflib.namespace import RDF, RDFS

from .desc import (
    graph,
    definition,
    note,
    example,
    has_type,
    subclass,
)
from .util import blank


def test_definition():
    with graph() as g:
        subj = blank()
        definition("A test definition")
        assert (
            subj,
            SKOS.definition,
            Literal("A test definition", lang="en"),
        ) in g

        # Test with different language
        definition("Une définition", lang="fr")
        assert (
            subj,
            SKOS.definition,
            Literal("Une définition", lang="fr"),
        ) in g


def test_note():
    with graph() as g:
        subj = blank()
        note("A test note")
        assert (
            subj,
            SKOS.note,
            Literal("A test note", lang="en"),
        ) in g

        # Test with different language
        note("Una nota", lang="es")
        assert (
            subj,
            SKOS.note,
            Literal("Una nota", lang="es"),
        ) in g


def test_example():
    with graph() as g:
        subj = blank()
        example("A test example")
        assert (
            subj,
            SKOS.example,
            Literal("A test example", lang="en"),
        ) in g

        # Test with different language
        example("Ett exempel", lang="sv")
        assert (
            subj,
            SKOS.example,
            Literal("Ett exempel", lang="sv"),
        ) in g


def test_rdf_type():
    with graph() as g:
        subj = blank()
        test_type = URIRef("http://example.org/TestType")
        has_type(test_type)
        assert (subj, RDF.type, test_type) in g


def test_subclass():
    with graph() as g:
        subj = blank()
        # Test with URIRef
        parent_class = URIRef("http://example.org/ParentClass")
        subclass(parent_class)
        assert (subj, RDFS.subClassOf, parent_class) in g

        # Test with string URI
        subclass("http://example.org/AnotherParentClass")
        assert (
            subj,
            RDFS.subClassOf,
            URIRef("http://example.org/AnotherParentClass"),
        ) in g
