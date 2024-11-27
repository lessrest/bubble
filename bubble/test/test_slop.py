import pytest
from anthropic import TextEvent
from bubble.slop import stream_sentences, stream_normally
import hypothesis.strategies as st
from hypothesis import given

sentence_ending_punctuation = st.sampled_from(".!?")

sentence = st.text("abc, \n").flatmap(
    lambda text: sentence_ending_punctuation.map(
        lambda punctuation: text + punctuation
    )
)


def create_text_stream(*chunks):
    """Create a mock Anthropic text stream from text chunks"""
    return [
        TextEvent(type="text", text=chunk, snapshot="")
        for chunk in chunks
    ]


@pytest.fixture
def text_stream():
    """Create a mock Anthropic text stream"""
    return create_text_stream(
        "First sentence",
        ". ",
        "Second ",
        "sentence. ",
        "Third sentence.",
    )


async def test_stream_sentences(text_stream):
    """Test streaming sentences"""
    sentences = []
    async for sentence in stream_sentences(text_stream):
        sentences.append(sentence)

    assert sentences == [
        "First sentence.",
        "Second sentence.",
        "Third sentence.",
    ]


async def test_stream_normally(text_stream):
    """Test normal streaming without sentence parsing"""
    result = await stream_normally(text_stream)

    expected = "First sentence. " "Second sentence. " "Third sentence."

    assert result == expected


@given(st.text())
async def test_sentence_stream_yields_same_text(text: str):
    events = create_text_stream(text)
    sentences = [
        sentence async for sentence in stream_sentences(events)
    ]
    assert "".join(sentences).strip() == text.strip()


@given(st.lists(sentence))
async def test_sentence_stream_on_list_of_sentences(
    sentences: list[str],
):
    events = create_text_stream(" ".join(sentences))
    streamed = [sentence async for sentence in stream_sentences(events)]
    assert streamed == sentences


@given(st.lists(sentence))
async def test_sentence_stream_on_list_of_sentences_with_newlines(
    sentences: list[str],
):
    events = create_text_stream("\n".join(sentences))
    streamed = [sentence async for sentence in stream_sentences(events)]
    assert streamed == sentences


async def test_sentence_stream_handles_no_sentence_ending():
    events = create_text_stream("This is a test")
    sentences = [
        sentence async for sentence in stream_sentences(events)
    ]
    assert sentences == ["This is a test"]


async def test_sentence_stream_handles_ellipsis():
    events = create_text_stream("This is a test... This is a test.")
    sentences = [
        sentence async for sentence in stream_sentences(events)
    ]
    assert sentences == ["This is a test...", "This is a test."]


async def test_sentence_stream_handles_newlines():
    events = create_text_stream("This is a test.\nThis is a test.")
    sentences = [
        sentence async for sentence in stream_sentences(events)
    ]
    assert sentences == ["This is a test.", "This is a test."]


@given(
    sentence.flatmap(
        lambda s: st.integers(1, len(s)).map(lambda n: (s, n))
    )
)
async def test_foo(x):
    (sentence, n) = x
    a = sentence[:n]
    b = sentence[n:]
    assert a + b == sentence
    events = create_text_stream(a, b)
    streamed = [sentence async for sentence in stream_sentences(events)]
    assert streamed == [sentence]
