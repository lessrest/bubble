import os
import tempfile

from trio import Path
from rdflib import RDF, Literal, Namespace
from rdflib.namespace import PROV

from swash.util import new
from bubble.logs import configure_logging
from bubble.repo.git import Git
from bubble.repo.repo import FROTH, Repository, context

logger = configure_logging()

# Define namespace at module level
EX = Namespace("https://example.org/")


async def test_graph_repo_basics():
    with tempfile.TemporaryDirectory() as workdir:
        git = Git(Path(workdir))
        repo = await Repository.create(git, base_url_template=EX)

        # Create initial graph and add data
        with repo.using_new_buffer() as graph_id:
            subject = new(EX.Type, {EX.label: Literal("Test")})
            assert graph_id in repo.list_graphs()
            await repo.save_all()

        # Test loading in new repo instance
        repo2 = await Repository.create(git, base_url_template=EX)
        await repo2.load_all()

        # Verify loaded data
        graph2 = repo2.graph(graph_id)
        assert len(graph2) == 2
        assert (subject, RDF.type, EX.Type) in graph2

        # Test git operations
        await repo2.commit("Test commit")
        assert os.path.exists(os.path.join(workdir, "void.ttl"))
        assert os.path.exists(
            os.path.join(workdir, repo.graph_file(graph_id))
        )


async def test_graph_repo_new_derived_graph():
    """Test deriving graphs with explicit and current context parameters"""
    with tempfile.TemporaryDirectory() as workdir:
        git = Git(Path(workdir))
        repo = await Repository.create(git, base_url_template=EX)

        # Create source graph
        with repo.using_new_buffer() as source_graph_id:
            new(EX.Type, {EX.label: Literal("Test")})

        # Test explicit derivation
        activity = EX.activity1
        with repo.using_derived_buffer(
            source_graph_id, activity=activity
        ) as derived_graph_id:
            x = new(EX.Type, {EX.label: Literal("Derived")})

        # Verify derived content
        derived_graph = repo.graph(derived_graph_id)
        assert (x, EX.label, Literal("Derived")) in derived_graph

        # Verify provenance
        assert (
            derived_graph_id,
            PROV.qualifiedDerivation,
            list(repo.metadata.subjects(RDF.type, FROTH.GraphDerivation))[
                0
            ],
        ) in repo.metadata

        # Test derivation with current context
        with context.bind_graph(source_graph_id, repo):
            current_act = EX.currentActivity
            with context.activity.bind(current_act):
                with repo.using_derived_buffer() as derived_graph_id2:
                    new(EX.Type, {EX.label: Literal("Derived2")})

                # Verify provenance with current context
                assert (
                    derived_graph_id2,
                    PROV.qualifiedDerivation,
                    list(
                        repo.metadata.subjects(
                            RDF.type, FROTH.GraphDerivation
                        )
                    )[1],
                ) in repo.metadata


async def test_graph_repo_new_graph():
    with tempfile.TemporaryDirectory() as workdir:
        git = Git(Path(workdir))
        repo = await Repository.create(git, base_url_template=EX)

        # Create new graph and add data
        with repo.using_new_buffer() as graph_id:
            new(EX.Type, {EX.label: Literal("Test")})

            # Verify graph contents
            graph = repo.graph(graph_id)
            assert len(graph) == 2  # type + label
            assert any(p == RDF.type and o == EX.Type for _, p, o in graph)
            assert any(
                p == EX.label and o == Literal("Test") for _, p, o in graph
            )

            # Verify registration
            assert graph_id in repo.list_graphs()


async def test_graph_repo_add_with_current_graph():
    with tempfile.TemporaryDirectory() as workdir:
        git = Git(Path(workdir))
        repo = await Repository.create(git, base_url_template=EX)

        # Test adding with current graph
        with repo.using_new_buffer() as graph_id:
            new(EX.Type, {EX.label: Literal("Test")})

            # Verify immediate state
            graph = repo.graph(graph_id)
            assert len(graph) == 2  # type + label
            assert any(p == RDF.type and o == EX.Type for _, p, o in graph)
            assert any(
                p == EX.label and o == Literal("Test") for _, p, o in graph
            )

        # Test persistence
        await repo.save_all()
        repo2 = await Repository.create(git, base_url_template=EX)
        await repo2.load_all()

        graph2 = repo2.graph(graph_id)
        assert len(graph2) == 2
        assert any(p == RDF.type and o == EX.Type for _, p, o in graph2)
        assert any(
            p == EX.label and o == Literal("Test") for _, p, o in graph2
        )
