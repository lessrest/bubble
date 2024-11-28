import logging
import pytest
import trio
from rdflib import Graph, URIRef, RDF
from bubble.repo import using_bubble_at
from bubble.prfx import NT
from bubble.util import print_n3
from bubble.vars import current_graph

logger = logging.getLogger(__name__)


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

    print_n3(current_graph.get())
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
    email = str(
        temp_repo.graph.value(temp_repo.bubble, NT.emailAddress)
    )
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
