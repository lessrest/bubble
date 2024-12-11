from datetime import UTC, datetime
from rdflib import SKOS, Graph, Namespace, Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD

from swash.rdf import (
    a,
    definition,
    example,
    graph,
    resource,
    property,
    literal,
    note,
    subclass,
)
from swash.util import print_n3

# Test namespace
TEST = Namespace("http://example.org/test#")


def test_simple_triple():
    with graph() as g:
        with resource() as subj:
            subj.add(TEST.name, "Test")

        print_n3(g)

        assert (None, TEST.name, Literal("Test")) in g


def test_typed_subject():
    with graph() as g:
        with resource(TEST.Person) as person:
            person.add(TEST.name, "Alice")
            subject = person.node

        assert (subject, RDF.type, TEST.Person) in g
        assert (subject, TEST.name, Literal("Alice")) in g


def test_nested_subjects():
    with graph() as g:
        with resource(TEST.Person) as person:
            person.add(TEST.name, "Alice")
            alice = person.node

            with property(TEST.knows) as friend:
                a(TEST.Person)
                property(TEST.name, "Bob")
                bob = friend.node

        assert (alice, TEST.knows, bob) in g


def test_literal_with_datatype():
    with graph() as g:
        with resource() as subj:
            subj.add(TEST.age, literal(42, datatype=XSD.integer))

        assert (subj.node, TEST.age, Literal(42, datatype=XSD.integer)) in g


def test_datetime_implict_datatype():
    with graph() as g:
        t = datetime.now(UTC)
        with resource() as subj:
            subj.add(TEST.created, t)

        assert (
            subj.node,
            TEST.created,
            Literal(t.isoformat(), datatype=XSD.dateTime),
        ) in g


def test_language_tagged_literal():
    with graph() as g:
        with resource() as subj:
            subj.add(RDFS.label, literal("Hello", lang="en"))
            subj.add(RDFS.label, literal("Bonjour", lang="fr"))

        assert (subj.node, RDFS.label, Literal("Hello", lang="en")) in g
        assert (subj.node, RDFS.label, Literal("Bonjour", lang="fr")) in g


def test_complex_structure():
    """Test a more complex data structure similar to describe_machine"""
    with graph() as g:
        with resource(TEST.Machine):
            with property(TEST.part):
                a(TEST.CPU)
                property(TEST.architecture, "x86_64")

            with property(TEST.part):
                a(TEST.RAM)
                property(TEST.size, 16)

            with property(TEST.system):
                a(TEST.OS)
                property(TEST.name, "Linux")
                property(TEST.version, "5.15.0")

        expected = """
            @prefix test: <http://example.org/test#> .
            @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

            [] a test:Machine ;
                test:part [ a test:CPU ;
                           test:architecture "x86_64" ],
                         [ a test:RAM ;
                           test:size "16"^^xsd:integer ] ;
                test:system [ a test:OS ;
                            test:name "Linux" ;
                            test:version "5.15.0" ] .
        """

        assert g.isomorphic(Graph().parse(data=expected, format="turtle"))


def test_definition():
    with graph() as g:
        with resource() as subj:
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
        with resource() as subj:
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
        with resource() as subj:
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
        with resource() as subj:
            test_type = URIRef("http://example.org/TestType")
            a(test_type)
            assert (subj.node, RDF.type, test_type) in g


def test_subclass():
    with graph() as g:
        with resource() as subj:
            # Test with URIRef
            parent_class = URIRef("http://example.org/ParentClass")
            subclass(parent_class)

            assert (subj.node, RDFS.subClassOf, parent_class) in g
