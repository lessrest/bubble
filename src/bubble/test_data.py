import os
import tempfile
from rdflib import URIRef, Literal, RDF, Namespace
from rdflib.namespace import PROV
from swash.util import new
from bubble.data import FROTH
import pytest

from .data import Git, GraphRepo, context

from bubble.logs import configure_logging

logger = configure_logging()

# Define namespace at module level
EX = Namespace("http://example.org/")


async def test_graph_repo_basics():
    with tempfile.TemporaryDirectory() as workdir:
        git = Git(workdir)
        repo = GraphRepo(git, namespace=EX)

        # Create initial graph and add data
        with repo.new_graph() as graph_id:
            subject = new(EX.Type, {EX.label: Literal("Test")})
            assert graph_id in repo.list_graphs()
            await repo.save_all()

        # Test loading in new repo instance
        repo2 = GraphRepo(git, namespace=EX)
        await repo2.load_all()

        # Verify loaded data
        graph2 = repo2.graph(graph_id)
        assert len(graph2) == 2
        assert (subject, RDF.type, EX.Type) in graph2

        # Test git operations
        await repo2.commit("Test commit")
        assert os.path.exists(os.path.join(workdir, "void.ttl"))
        assert os.path.exists(
            os.path.join(workdir, repo.graph_filename(graph_id))
        )


async def test_graph_repo_new_derived_graph():
    """Test deriving graphs with explicit and current context parameters"""
    with tempfile.TemporaryDirectory() as workdir:
        git = Git(workdir)
        repo = GraphRepo(git, namespace=EX)

        # Create source graph
        with repo.new_graph() as source_graph_id:
            repo.add((EX.subject, RDF.type, EX.Type))

        # Test explicit derivation
        activity = EX.activity1
        with repo.new_derived_graph(
            source_graph_id, activity=activity
        ) as derived_graph_id:
            repo.add((EX.subject, EX.label, Literal("Derived")))

        # Verify derived content
        derived_graph = repo.graph(derived_graph_id)
        assert (EX.subject, EX.label, Literal("Derived")) in derived_graph

        # Verify provenance
        assert (
            derived_graph_id,
            PROV.qualifiedDerivation,
            list(repo.metadata.subjects(RDF.type, FROTH.GraphDerivation))[0],
        ) in repo.metadata

        # Test derivation with current context
        with context.graph.bind(repo.graph(source_graph_id)):
            current_act = EX.currentActivity
            with context.activity.bind(current_act):
                with repo.new_derived_graph() as derived_graph_id2:
                    repo.add((EX.subject, EX.label, Literal("Derived2")))

                # Verify provenance with current context
                assert (
                    derived_graph_id2,
                    PROV.qualifiedDerivation,
                    list(repo.metadata.subjects(RDF.type, FROTH.GraphDerivation))[1],
                ) in repo.metadata


async def test_graph_repo_new_graph():
    with tempfile.TemporaryDirectory() as workdir:
        git = Git(workdir)
        repo = GraphRepo(git, namespace=EX)

        # Create new graph and add data
        with repo.new_graph() as graph_id:
            repo.add((EX.subject, RDF.type, EX.Type))
            repo.add((EX.subject, EX.label, Literal("Test")))

            # Verify graph contents
            graph = repo.graph(graph_id)
            assert len(graph) == 2
            assert (EX.subject, RDF.type, EX.Type) in graph
            assert (EX.subject, EX.label, Literal("Test")) in graph

            # Verify registration
            assert graph_id in repo.list_graphs()


async def test_graph_repo_add_with_current_graph():
    with tempfile.TemporaryDirectory() as workdir:
        git = Git(workdir)
        repo = GraphRepo(git, namespace=EX)

        # Test error when no current graph
        with pytest.raises(ValueError, match="No current graph set"):
            repo.add((EX.subject, RDF.type, EX.Type))

        # Test adding with current graph
        with repo.new_graph() as graph_id:
            repo.add((EX.subject, RDF.type, EX.Type))
            repo.add((EX.subject, EX.label, Literal("Test")))

            # Verify immediate state
            graph = repo.graph(graph_id)
            assert len(graph) == 2
            assert (EX.subject, RDF.type, EX.Type) in graph
            assert (EX.subject, EX.label, Literal("Test")) in graph

        # Test persistence
        await repo.save_all()
        repo2 = GraphRepo(git, namespace=EX)
        await repo2.load_all()

        graph2 = repo2.graph(graph_id)
        assert len(graph2) == 2
        assert (EX.subject, RDF.type, EX.Type) in graph2
