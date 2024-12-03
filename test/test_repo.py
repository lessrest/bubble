import pytest
import structlog
import trio
from rdflib import Graph, URIRef, RDF
from bubble.repo import using_bubble_at
from bubble.prfx import NT
from bubble.util import get_single_subject, print_n3

from bubble import vars

logger = structlog.get_logger()


@pytest.fixture
async def temp_repo(tmp_path):
    """Create a temporary repository for testing"""
    async with using_bubble_at(tmp_path) as repo:
        yield repo


async def test_repo_initialization(temp_repo):
    """Test that a new repository is properly initialized"""
    logger.info("Testing repo initialization for %s", temp_repo.bubble)

    # Verify basic repo properties
    assert isinstance(temp_repo.bubble, URIRef)
    assert isinstance(temp_repo.graph, Graph)
    assert await trio.Path(temp_repo.workdir).exists()
    assert await trio.Path(temp_repo.rootpath).exists()

    # Verify git initialization
    assert await trio.Path(temp_repo.workdir / ".git").exists()

    print_n3(vars.graph.get())
    print_n3(temp_repo.graph)

    # Verify bubble has type nt:Bubble
    assert (temp_repo.bubble, RDF.type, NT.Bubble) in temp_repo.graph


async def test_repo_load_surfaces(temp_repo):
    """Test loading surfaces into the repository"""
    # Create a test surface file
    surface_path = trio.Path(temp_repo.workdir) / "test.n3"
    await surface_path.write_text("""
        @prefix : <http://example.org/> .
        :TestSubject a :TestType .
    """)

    # Load surfaces and verify
    await temp_repo.load_surfaces()
    assert len(temp_repo.graph) > 0
    test_subject = URIRef("http://example.org/TestSubject")
    test_type = URIRef("http://example.org/TestType")
    assert (test_subject, RDF.type, test_type) in temp_repo.graph


async def test_repo_commit(temp_repo):
    """Test committing changes to the repository"""
    # Add a test file
    test_file = trio.Path(temp_repo.workdir) / "test.txt"
    await test_file.write_text("test content")

    # Commit changes
    await temp_repo.commit()

    # Verify git status
    result = await trio.run_process(
        ["git", "-C", str(temp_repo.workdir), "status", "--porcelain"],
        capture_stdout=True,
    )
    assert (
        result.stdout.decode().strip() == ""
    ), "Working directory should be clean"


async def test_repo_load_ontology(temp_repo):
    """Test loading ontology files"""
    await temp_repo.load_ontology()
    # Verify some basic ontology triples are present
    assert any(p == RDF.type for p in temp_repo.graph.predicates())


async def test_repo_load_rules(temp_repo):
    """Test loading rule files"""
    await temp_repo.load_rules()
    # Verify rules were loaded
    assert len(temp_repo.graph) > 0


async def test_repo_git_config(temp_repo):
    """Test that Git configuration is set correctly"""
    # Get the bubble's email from the graph
    email = str(temp_repo.graph.value(temp_repo.bubble, NT.emailAddress))
    assert email.endswith(
        "@swa.sh"
    ), f"Email '{email}' should end with @swa.sh"

    # Verify Git config
    result = await trio.run_process(
        ["git", "-C", str(temp_repo.workdir), "config", "user.name"],
        capture_stdout=True,
    )
    assert result.stdout.decode().strip() == "Bubble"

    result = await trio.run_process(
        ["git", "-C", str(temp_repo.workdir), "config", "user.email"],
        capture_stdout=True,
    )
    assert result.stdout.decode().strip() == email


async def test_repo_separate_graphs(temp_repo):
    """Test that vocab and data are kept in separate graphs"""
    # Load some test data into main graph
    test_file = trio.Path(temp_repo.workdir) / "test.n3"
    await test_file.write_text("""
        @prefix : <http://example.org/> .
        :TestSubject a :TestType .
    """)
    await temp_repo.load_surfaces()

    # Load ontology into vocab graph
    await temp_repo.load_ontology()

    # Get initial sizes
    data_size = len(temp_repo.graph)
    vocab_size = len(temp_repo.vocab)

    assert data_size > 0, "Data graph should not be empty"
    assert vocab_size > 0, "Vocab graph should not be empty"

    # Reload ontology
    await temp_repo.load_ontology()

    # Verify data graph was unaffected
    assert (
        len(temp_repo.graph) == data_size
    ), "Data graph should be unchanged"
    assert (
        len(temp_repo.vocab) == vocab_size
    ), "Vocab should reload to same size"


async def test_repo_dataset(temp_repo):
    """Test that the dataset properly manages multiple graphs"""
    # Load some test data into main graph
    test_file = trio.Path(temp_repo.workdir) / "test.n3"
    await test_file.write_text("""
        @prefix : <http://example.org/> .
        :TestSubject a :TestType .
    """)
    await temp_repo.load_surfaces()

    # Load ontology into vocab graph
    await temp_repo.load_ontology()

    # Verify graphs are in dataset
    assert temp_repo.graph.identifier == URIRef(
        "https://node.town/2024/bubble"
    )
    assert temp_repo.vocab.identifier == URIRef(
        "https://node.town/2024/vocabulary"
    )

    # Verify we can get graphs from dataset
    assert temp_repo.dataset.graph(NT.bubble) == temp_repo.graph
    assert temp_repo.dataset.graph(NT.vocabulary) == temp_repo.vocab

    # Verify data is in correct graphs
    assert len(temp_repo.graph) > 0
    assert len(temp_repo.vocab) > 0

    # Test quads access
    quads = list(temp_repo.dataset.quads((None, None, None, None)))
    assert len(quads) == len(temp_repo.graph) + len(temp_repo.vocab)


def test_get_single_subject():
    """Test getting a single subject from a triple pattern"""
    g = vars.graph.get()
    g.add((URIRef("s"), URIRef("p"), URIRef("o")))
    assert get_single_subject(URIRef("p"), URIRef("o")) == URIRef("s")
