from rdflib import Namespace, Literal
from rdflib.namespace import RDF, RDFS, XSD

from swash.rdf import graph, new, add, has, literal
from swash.util import print_n3

# Test namespace
TEST = Namespace("http://example.org/test#")


def test_simple_triple():
    with graph() as g:
        with new() as subj:
            subj.has(TEST.name, "Test")

        assert (None, TEST.name, Literal("Test")) in g


def test_typed_subject():
    with graph() as g:
        with new(TEST.Person) as person:
            person.has(TEST.name, "Alice")
            subject = person.node

        assert (subject, RDF.type, TEST.Person) in g
        assert (subject, TEST.name, Literal("Alice")) in g


def test_nested_subjects():
    with graph() as g:
        with new(TEST.Person) as person:
            person.has(TEST.name, "Alice")
            alice = person.node

            with add(TEST.knows) as friend:
                friend.has(RDF.type, TEST.Person)
                friend.has(TEST.name, "Bob")
                bob = friend.node

        assert (alice, TEST.knows, bob) in g


def test_literal_with_datatype():
    with graph() as g:
        with new() as subj:
            subj.has(TEST.age, literal(42, datatype=XSD.integer))

        assert (subj.node, TEST.age, Literal(42, datatype=XSD.integer)) in g


def test_language_tagged_literal():
    with graph() as g:
        with new() as subj:
            subj.has(RDFS.label, literal("Hello", lang="en"))
            subj.has(RDFS.label, literal("Bonjour", lang="fr"))

        assert (subj.node, RDFS.label, Literal("Hello", lang="en")) in g
        assert (subj.node, RDFS.label, Literal("Bonjour", lang="fr")) in g


def test_complex_structure():
    """Test a more complex data structure similar to describe_machine"""
    with graph() as g:
        with new(TEST.Machine) as machine:
            machine_node = machine.node

            # Add CPU
            with add(TEST.part) as cpu:
                has(RDF.type, TEST.CPU)
                has(TEST.architecture, "x86_64")
                cpu_node = cpu.node

            # Add RAM
            with add(TEST.part) as ram:
                has(RDF.type, TEST.RAM)
                has(TEST.size, literal(16, datatype=XSD.integer))
                ram_node = ram.node

            # Add OS
            with add(TEST.system) as os:
                has(RDF.type, TEST.OS)
                has(TEST.name, "Linux")
                has(TEST.version, "5.15.0")
                os_node = os.node

        # Verify machine type
        assert (machine_node, RDF.type, TEST.Machine) in g

        # Verify parts
        parts = list(g.objects(machine_node, TEST.part))
        assert len(parts) == 2
        assert cpu_node in parts
        assert ram_node in parts

        # Verify CPU
        print_n3(g)
        assert (cpu_node, RDF.type, TEST.CPU) in g
        assert (cpu_node, TEST.architecture, Literal("x86_64")) in g

        # Verify RAM
        assert (ram_node, RDF.type, TEST.RAM) in g
        assert (
            ram_node,
            TEST.size,
            Literal(16, datatype=XSD.integer),
        ) in g

        # Verify OS
        assert (os_node, RDF.type, TEST.OS) in g
        assert (os_node, TEST.name, Literal("Linux")) in g
        assert (os_node, TEST.version, Literal("5.15.0")) in g
