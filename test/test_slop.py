from typing import AsyncGenerator

import pytest
import hypothesis.strategies as st

from hypothesis import given

from bubble.slop import stream_normally, stream_sentences

sentence_ending_punctuation = st.sampled_from(".!?")

sentence = st.text("abc, \n").flatmap(
    lambda text: sentence_ending_punctuation.map(
        lambda punctuation: text + punctuation
    )
)


async def create_text_stream(*chunks: str) -> AsyncGenerator[str, None]:
    """Create a mock Anthropic text stream from text chunks"""
    for chunk in chunks:
        yield chunk


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
        "First sentence. ",
        "Second sentence. ",
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
    sentences = [sentence async for sentence in stream_sentences(events)]
    assert "".join(sentences).strip() == text.strip()


@given(st.lists(sentence))
async def test_sentence_stream_on_list_of_sentences(
    sentences: list[str],
):
    events = create_text_stream(" ".join(sentences))
    streamed = [
        sentence.strip() async for sentence in stream_sentences(events)
    ]
    assert streamed == [sentence.strip() for sentence in sentences]


@given(st.lists(sentence))
async def test_sentence_stream_on_list_of_sentences_with_newlines(
    sentences: list[str],
):
    events = create_text_stream("\n".join(sentences))
    streamed = [
        sentence.strip() async for sentence in stream_sentences(events)
    ]
    assert streamed == [sentence.strip() for sentence in sentences]


async def test_sentence_stream_handles_no_sentence_ending():
    events = create_text_stream("This is a test")
    sentences = [
        sentence.strip() async for sentence in stream_sentences(events)
    ]
    assert sentences == ["This is a test"]


async def test_sentence_stream_handles_ellipsis():
    events = create_text_stream("This is a test... This is a test.")
    sentences = [
        sentence.strip() async for sentence in stream_sentences(events)
    ]
    assert sentences == ["This is a test...", "This is a test."]


async def test_sentence_stream_handles_newlines():
    events = create_text_stream("This is a test.\nThis is a test.")
    sentences = [sentence async for sentence in stream_sentences(events)]
    assert sentences == ["This is a test.\n", "This is a test."]


@given(
    sentence.flatmap(lambda s: st.integers(1, len(s)).map(lambda n: (s, n)))
)
async def test_foo(x):
    (sentence, n) = x
    a = sentence[:n]
    b = sentence[n:]
    assert a + b == sentence
    events = create_text_stream(a, b)
    streamed = [sentence async for sentence in stream_sentences(events)]
    assert streamed == [sentence]
