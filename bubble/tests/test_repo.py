import pytest
import trio
from rdflib import Graph, URIRef, RDF
from bubble.repo import BubbleRepo
from bubble.mint import Mint


@pytest.fixture
async def temp_repo(tmp_path):
    """Create a temporary repository for testing"""
    repo = await BubbleRepo.open(trio.Path(tmp_path))
    return repo


@pytest.mark.trio
async def test_repo_initialization(temp_repo):
    """Test that a new repository is properly initialized"""
    # Verify basic repo properties
    assert isinstance(temp_repo.bubble, URIRef)
    assert isinstance(temp_repo.graph, Graph)
    assert await trio.Path(temp_repo.workdir).exists()
    assert await trio.Path(temp_repo.rootpath).exists()

    # Verify git initialization
    assert await trio.Path(temp_repo.workdir / ".git").exists()


@pytest.mark.trio
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


@pytest.mark.trio
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


@pytest.mark.trio
async def test_repo_load_ontology(temp_repo):
    """Test loading ontology files"""
    await temp_repo.load_ontology()
    # Verify some basic ontology triples are present
    assert any(p == RDF.type for p in temp_repo.graph.predicates())


@pytest.mark.trio
async def test_repo_load_rules(temp_repo):
    """Test loading rule files"""
    await temp_repo.load_rules()
    # Verify rules were loaded
    assert len(temp_repo.graph) > 0
