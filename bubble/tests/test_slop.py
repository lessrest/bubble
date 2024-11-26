import pytest
from anthropic import TextEvent
from bubble.slop import stream_sentences, stream_normally


@pytest.fixture
def text_stream():
    """Create a mock Anthropic text stream"""
    events = [
        TextEvent(
            type="text", text="<sentence>First sentence", snapshot=""
        ),
        TextEvent(type="text", text=".</sentence> ", snapshot=""),
        TextEvent(type="text", text="<sentence>Second ", snapshot=""),
        TextEvent(
            type="text", text="sentence.</sentence>", snapshot=""
        ),
        TextEvent(
            type="text", text="<sentence>Third sentence.", snapshot=""
        ),
    ]
    return events


@pytest.mark.trio
async def test_stream_sentences(text_stream):
    """Test streaming sentences with XML tags"""
    result = await stream_sentences(text_stream)

    expected = (
        "First sentence\n\n" "Second sentence\n\n" "Third sentence"
    )

    assert result == expected


@pytest.mark.trio
async def test_stream_sentences_with_initial(text_stream):
    """Test streaming with initial partial sentence"""
    result = await stream_sentences(
        text_stream, initial_sentence="<sentence>Initial "
    )

    assert result.startswith("Initial")


@pytest.mark.trio
async def test_stream_normally(text_stream):
    """Test normal streaming without sentence parsing"""
    result = await stream_normally(text_stream)

    expected = (
        "<sentence>First sentence.</sentence> "
        "<sentence>Second sentence.</sentence>"
        "<sentence>Third sentence.</sentence>"
    )

    assert result == expected


@pytest.mark.trio
async def test_stream_multiline_sentences(capsys):
    """Test handling of multiline sentence content"""
    events = [
        TextEvent(
            type="text",
            text="<sentence>First\nline\nof text.",
            snapshot="",
        ),
    ]

    result = await stream_sentences(events)
    assert result == "First line of text"
