import pytest
from anthropic import TextEvent
from bubble.slop import stream_sentences, stream_normally


def create_text_stream(*chunks):
    """Create a mock Anthropic text stream from text chunks"""
    return [TextEvent(type="text", text=chunk, snapshot="") for chunk in chunks]

@pytest.fixture
def text_stream():
    """Create a mock Anthropic text stream"""
    return create_text_stream(
        "<sentence>First sentence",
        ".</sentence> ",
        "<sentence>Second ",
        "sentence.</sentence>",
        "<sentence>Third sentence."
    )


@pytest.mark.trio
async def test_stream_sentences(text_stream):
    """Test streaming sentences with XML tags"""
    sentences = []
    async for sentence in stream_sentences(text_stream):
        sentences.append(sentence)

    assert sentences == [
        "First sentence",
        "Second sentence",
        "Third sentence"
    ]


@pytest.mark.trio
async def test_stream_sentences_with_initial(text_stream):
    """Test streaming with initial partial sentence"""
    sentences = []
    async for sentence in stream_sentences(
        text_stream, initial_sentence="<sentence>Initial "
    ):
        sentences.append(sentence)

    assert sentences[0].startswith("Initial")


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
async def test_stream_multiline_sentences():
    """Test handling of multiline sentence content"""
    events = create_text_stream("<sentence>First\nline\nof text.")

    sentences = []
    async for sentence in stream_sentences(events):
        sentences.append(sentence)
    
    assert sentences == ["First line of text"]
