from datetime import UTC, datetime

import pytest
import structlog
import trio
from rdflib import Graph, Literal, URIRef, RDF
from bubble.repo import using_bubble_at
from swash.prfx import NT
from swash.util import (
    get_single_subject,
    new,
    print_n3,
    select_one_row,
    select_rows,
)

from swash import vars

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
    surface_path = trio.Path(temp_repo.workdir) / "root.n3"
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


@pytest.mark.skip("we're not saving arbitrary files yet")
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


async def test_repo_blob_storage(temp_repo):
    """Test blob storage operations in the repository"""
    # Test data
    stream_id = URIRef("test_stream")
    test_data = [b"test data 1", b"test data 2", b"test data 3"]
    stream = temp_repo.blob(stream_id)

    # Test appending blobs
    for seq, data in enumerate(test_data):
        stream.write(data)

    # Test getting last sequence
    assert stream.get_last_sequence() == len(test_data) - 1

    # Test getting blobs
    retrieved_blobs = list(stream[0 : len(test_data)])
    assert retrieved_blobs == test_data

    # Test getting streams with blobs
    streams = temp_repo.get_streams_with_blobs()
    assert len(streams) == 1
    assert streams[0] == stream_id

    # Test getting partial range
    partial_blobs = list(stream[1:3])
    assert partial_blobs == test_data[1:3]

    # Test getting single part
    assert stream[1] == test_data[1]

    # Test deleting stream
    stream.delete()
    assert stream.get_last_sequence() == -1
    assert list(stream[0 : len(test_data)]) == []
    assert temp_repo.get_streams_with_blobs() == []


async def test_repo_blob_persistence(temp_repo):
    """Test that blobs persist across repository instances"""
    # Add test data
    stream_id = URIRef("test_stream")
    test_data = b"persistent data"
    temp_repo.blob(stream_id).write(test_data)

    # Create new repo instance with same path
    async with using_bubble_at(temp_repo.workdir) as new_repo:
        # Verify data persists
        stream = new_repo.blob(stream_id)
        retrieved_data = stream[0]
        assert retrieved_data == test_data
        assert stream.get_last_sequence() == 0
        assert new_repo.get_streams_with_blobs()[0] == stream_id


async def test_repo_multiple_streams(temp_repo):
    """Test handling multiple blob streams"""
    streams = [URIRef("stream1"), URIRef("stream2"), URIRef("stream3")]
    test_data = b"test data"

    # Add data to multiple streams
    for stream_id in streams:
        temp_repo.blob(stream_id).write(test_data)

    # Verify all streams are present
    stored_streams = temp_repo.get_streams_with_blobs()
    assert len(stored_streams) == len(streams)
    assert all(s in streams for s in stored_streams)

    # Verify data in each stream
    for stream_id in streams:
        stream = temp_repo.blob(stream_id)
        assert stream[0] == test_data
        assert stream.get_last_sequence() == 0


async def test_repo_blob_sequence_order(temp_repo):
    """Test that blob sequences are maintained in order"""
    stream_id = URIRef("test_stream")
    test_data = [b"data1", b"data2", b"data3"]
    stream = temp_repo.blob(stream_id)

    # Add data in reverse order
    for seq in range(len(test_data)):
        stream.write(test_data[seq])

    # Verify retrieval order
    retrieved = list(stream[0 : len(test_data)])
    assert retrieved == test_data


async def test_typed_blob_stream(temp_repo):
    """Test creating and using a typed blob stream"""
    # Create a test stream with type
    stream_id = URIRef("test_stream")
    stream_type = URIRef("http://example.org/TestType")

    # Add stream metadata
    new(
        NT.BlobStream,
        {
            NT.wasCreatedAt: Literal(datetime.now(UTC)),
            NT.hasPacketType: stream_type,
        },
        stream_id,
    )

    # Add some test data
    stream = temp_repo.blob(stream_id)
    test_data = b"test packet data"
    stream.write(test_data)

    # Verify stream type
    stream_type_result = select_one_row(
        """
        SELECT ?type WHERE {
            ?stream nt:hasPacketType ?type .
        }
        """,
        bindings={"stream": stream_id},
    )[0]

    assert stream_type_result == stream_type
    assert stream[0] == test_data


async def test_opus_stream_creation(temp_repo):
    """Test creating an Opus audio stream"""
    # Create a test stream with Opus type
    stream_id = URIRef("test_opus_stream")

    # Add stream metadata
    new(
        NT.BlobStream,
        {
            NT.wasCreatedAt: Literal(datetime.now(UTC)),
            NT.hasPacketType: NT.OpusPacket20ms,
        },
        subject=stream_id,
    )

    # Add audio-specific metadata
    new(
        NT.AudioPacketStream,
        {
            NT.hasSampleRate: Literal(48000),
            NT.hasChannelCount: Literal(1),
        },
        subject=stream_id,
    )

    # Verify stream type and audio metadata
    results = select_rows(
        """
        SELECT ?type ?rate ?channels WHERE {
            ?stream nt:hasPacketType ?type ;
                    nt:hasSampleRate ?rate ;
                    nt:hasChannelCount ?channels .
        }
        """,
        bindings={"stream": stream_id},
    )

    assert len(results) == 1
    stream_type, sample_rate, channels = results[0]
    assert stream_type == NT.OpusPacket20ms
    assert int(sample_rate) == 48000
    assert int(channels) == 1
