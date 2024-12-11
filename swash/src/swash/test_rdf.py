from rdflib import SKOS, URIRef, Literal
from rdflib.namespace import RDF, RDFS

from .rdf import graph, new, definition, note, example, a, subclass


def test_definition():
    with graph() as g:
        with new() as subj:
            definition("A test definition")
            assert (
                subj.node,
                SKOS.definition,
                Literal("A test definition", lang="en"),
            ) in g

            # Test with different language
            definition("Une définition", lang="fr")
            assert (
                subj.node,
                SKOS.definition,
                Literal("Une définition", lang="fr"),
            ) in g


def test_note():
    with graph() as g:
        with new() as subj:
            note("A test note")
            assert (
                subj.node,
                SKOS.note,
                Literal("A test note", lang="en"),
            ) in g

            # Test with different language
            note("Una nota", lang="es")
            assert (
                subj.node,
                SKOS.note,
                Literal("Una nota", lang="es"),
            ) in g


def test_example():
    with graph() as g:
        with new() as subj:
            example("A test example")
            assert (
                subj.node,
                SKOS.example,
                Literal("A test example", lang="en"),
            ) in g

            # Test with different language
            example("Ett exempel", lang="sv")
            assert (
                subj.node,
                SKOS.example,
                Literal("Ett exempel", lang="sv"),
            ) in g


def test_rdf_type():
    with graph() as g:
        with new() as subj:
            test_type = URIRef("http://example.org/TestType")
            a(test_type)
            assert (subj.node, RDF.type, test_type) in g


def test_subclass():
    with graph() as g:
        with new() as subj:
            # Test with URIRef
            parent_class = URIRef("http://example.org/ParentClass")
            subclass(parent_class)
            assert (subj.node, RDFS.subClassOf, parent_class) in g

            # Test with string URI
            subclass("http://example.org/AnotherParentClass")
            assert (
                subj.node,
                RDFS.subClassOf,
                URIRef("http://example.org/AnotherParentClass"),
            ) in g
