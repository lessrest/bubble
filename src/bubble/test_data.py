import os
import tempfile
from rdflib import URIRef, Literal, RDF, Namespace 
from rdflib.namespace import PROV
from bubble.data import FROTH
import pytest

from .data import Git, GraphRepo, context

from bubble.logs import configure_logging

logger = configure_logging()

# Define namespace at module level
EX = Namespace("http://example.org/")


async def test_graph_repo_basics():
    # Create a temporary directory for the test repo
    with tempfile.TemporaryDirectory() as workdir:
        # Initialize Git and GraphRepo
        git = Git(workdir)
        repo = GraphRepo(git, namespace=EX)

        # Create and populate a test graph
        graph_id = EX.test
        graph = repo.graph(graph_id)

        # Add some test triples
        subject = EX.subject
        graph.add((subject, RDF.type, EX.Type))
        graph.add((subject, EX.label, Literal("Test")))

        # Check that the graph is registered in metadata
        assert graph_id in repo.list_graphs()

        # Save everything
        await repo.save_all()

        # Create a new repo instance to test loading
        repo2 = GraphRepo(git, namespace=EX)
        await repo2.load_all()

        # Verify the loaded graph has our triples
        graph2 = repo2.graph(graph_id)
        assert len(graph2) == 2

        # Check specific triple exists
        assert (subject, RDF.type, EX.Type) in graph2

        # Commit changes
        await repo2.commit("Test commit")

        # Verify files exist in git
        assert os.path.exists(os.path.join(workdir, "void.ttl"))
        assert os.path.exists(
            os.path.join(workdir, "http___example.org_test.trig")
        )


async def test_graph_repo_new_derived_graph():
    """Test deriving graphs with explicit and current context parameters"""
    with tempfile.TemporaryDirectory() as workdir:
        git = Git(workdir)
        repo = GraphRepo(git, namespace=EX)

        # Create an initial graph
        source_graph_id = EX.source
        source_graph = repo.graph(source_graph_id)
        source_graph.add((EX.subject, RDF.type, EX.Type))

        # Test explicit source graph
        activity = EX.activity1
        with repo.new_derived_graph(source_graph_id, activity=activity) as derived_graph_id:
            repo.add((EX.subject, EX.label, Literal("Derived")))

        # Verify the derived graph contains our new triple
        derived_graph = repo.graph(derived_graph_id)
        assert (EX.subject, EX.label, Literal("Derived")) in derived_graph

        # Verify the provenance relations were recorded
        assert (derived_graph_id, PROV.wasDerivedFrom, source_graph_id) in repo.metadata
        assert (derived_graph_id, PROV.wasGeneratedBy, activity) in repo.metadata
        assert (source_graph_id, PROV.wasInfluencedBy, activity) in repo.metadata
        
        # Verify the derivation has our custom type
        derivations = list(repo.metadata.subjects(RDF.type, FROTH.GraphDerivation))
        assert len(derivations) == 1

        # Test deriving using current context
        with context.bind_graph(source_graph_id, repo):
            current_act = EX.currentActivity
            with context.activity.bind(current_act):
                with repo.new_derived_graph() as derived_graph_id2:
                    repo.add((EX.subject, EX.label, Literal("Derived2")))
            
                # Verify derivation using current context
                assert (derived_graph_id2, PROV.wasDerivedFrom, source_graph_id) in repo.metadata
                assert (derived_graph_id2, PROV.wasGeneratedBy, current_act) in repo.metadata
                assert (source_graph_id, PROV.wasInfluencedBy, current_act) in repo.metadata

async def test_graph_repo_new_graph():
    with tempfile.TemporaryDirectory() as workdir:
        git = Git(workdir)
        # Test with namespace
        repo = GraphRepo(git, namespace=EX)

        # Use the new_graph context manager
        with repo.new_graph() as graph_id:
            repo.add((EX.subject, RDF.type, EX.Type))
            repo.add((EX.subject, EX.label, Literal("Test")))

        # Verify the graph was created and contains our triples
        graph = repo.graph(graph_id)
        assert len(graph) == 2
        assert (EX.subject, RDF.type, EX.Type) in graph
        assert (EX.subject, EX.label, Literal("Test")) in graph

        # Verify the graph is registered in metadata
        assert graph_id in repo.list_graphs()

async def test_graph_repo_add_with_current_graph():
    # Create a temporary directory for the test repo
    with tempfile.TemporaryDirectory() as workdir:
        # Initialize Git and GraphRepo
        git = Git(workdir)
        repo = GraphRepo(git, namespace=EX)

        # Create a test graph
        graph_id = EX.test

        # Test that adding without setting current_graph raises error
        with pytest.raises(Exception):
            repo.add((EX.subject, RDF.type, EX.Type))

        # Set current graph and add a triple
        with context.bind_graph(graph_id, repo):
            repo.add((EX.subject, RDF.type, EX.Type))
            repo.add((EX.subject, EX.label, Literal("Test")))

        # Verify triples were added
        graph = repo.graph(graph_id)
        assert len(graph) == 2
        assert (EX.subject, RDF.type, EX.Type) in graph
        assert (EX.subject, EX.label, Literal("Test")) in graph

        # Save and reload to verify persistence
        await repo.save_all()
        repo2 = GraphRepo(git, namespace=EX)
        await repo2.load_all()

        graph2 = repo2.graph(graph_id)
        assert len(graph2) == 2
        assert (EX.subject, RDF.type, EX.Type) in graph2
